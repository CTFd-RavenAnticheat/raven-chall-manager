#!/bin/bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-unknown}"
IDENTITY="${IDENTITY:-unknown}"
LABEL="${LABEL:-}"
CAPTURE_DIR="${CAPTURE_DIR:-/captures}"
PORTS="${PORTS:-}"
MAX_SESSIONS=3
MAX_CAPTURE_SIZE=8192 # Set to 0 for full packet data
METADATA_FILE="${CAPTURE_DIR}/sessions.json"
CONNECTION_TIMEOUT=180
OWNED_GLOB="${CAPTURE_DIR}/*.pcap"

mkdir -p "${CAPTURE_DIR}"
[ ! -f "${METADATA_FILE}" ] && echo '{"sessions":[]}' > "${METADATA_FILE}"

log() { echo "[$(date -Iseconds)] $*" >&2; }

build_filter() {
    local filter=""
    IFS=',' read -ra PORT_ARRAY <<< "$PORTS"
    for port_proto in "${PORT_ARRAY[@]}"; do
        [ -z "$port_proto" ] && continue
        IFS=':' read -r port proto <<< "$port_proto"
        proto="${proto:-tcp}"
        [ -n "$filter" ] && filter="$filter or "
        filter="$filter (${proto} port ${port} and tcp[tcpflags] & tcp-push != 0)"
    done
    echo "$filter"
}

get_connection_count() {
    local total=0
    IFS=',' read -ra PORT_ARRAY <<< "$PORTS"
    for port_proto in "${PORT_ARRAY[@]}"; do
        [ -z "$port_proto" ] && continue
        local port="${port_proto%%:*}"
        local count
        count=$(ss -tan 2>/dev/null | grep ":${port} " | grep -c ESTAB || true)
        total=$((total + count))
    done
    echo "$total"
}

BPF_FILTER=$(build_filter)
log "Starting session capture: Container=$CONTAINER_NAME, Ports=$PORTS"

SESSION_ACTIVE=false
LAST_ACTIVITY=$(date +%s)
LAST_FILE_SIZE=0
CAPTURE_PID=0

cleanup() {
    if [ "$SESSION_ACTIVE" = true ] && [ "$CAPTURE_PID" -ne 0 ]; then
        kill -TERM "$CAPTURE_PID" 2>/dev/null || true
    fi
    exit 0
}
trap cleanup SIGTERM SIGINT

while true; do
    CONNECTION_COUNT=$(get_connection_count)
    CURRENT_TIME=$(date +%s)

    if [ "$SESSION_ACTIVE" = false ]; then
        if [ "$CONNECTION_COUNT" -gt 0 ]; then
            SESSION_ID=$(cat /proc/sys/kernel/random/uuid)
            SESSION_START=$(date -Iseconds)
            
            CAPTURE_FILE="${CAPTURE_DIR}/${IDENTITY}-${CONTAINER_NAME}-${SESSION_ID}.pcap"
            [ -n "$LABEL" ] && CAPTURE_FILE="${CAPTURE_DIR}/${LABEL}-${IDENTITY}-${CONTAINER_NAME}-${SESSION_ID}.pcap"
            
            log "New session: ${SESSION_ID} -> ${CAPTURE_FILE}"
            tcpdump -i eth0 -U -s $MAX_CAPTURE_SIZE -w "$CAPTURE_FILE" "$BPF_FILTER" &
            CAPTURE_PID=$!
            SESSION_ACTIVE=true
            LAST_ACTIVITY=$CURRENT_TIME
            LAST_FILE_SIZE=0
            continue
        fi
        sleep 0.1
    else
        # Monitor file growth to check for real activity (ignoring keep-alives)
        CURRENT_FILE_SIZE=$(stat -c%s "$CAPTURE_FILE" 2>/dev/null || echo 0)
        if [ "$CURRENT_FILE_SIZE" -gt "$LAST_FILE_SIZE" ]; then
            LAST_ACTIVITY=$CURRENT_TIME
            LAST_FILE_SIZE=$CURRENT_FILE_SIZE
        fi

        if [ $((CURRENT_TIME - LAST_ACTIVITY)) -ge $CONNECTION_TIMEOUT ]; then
            log "Session ended/timed out: ${SESSION_ID}"
            kill -TERM "$CAPTURE_PID" 2>/dev/null || true
            wait "$CAPTURE_PID" 2>/dev/null || true
            
            if [ -f "$CAPTURE_FILE" ]; then
                FILE_SIZE=$(stat -c%s "$CAPTURE_FILE" 2>/dev/null || echo 0)
                PACKET_COUNT=$(tcpdump -r "$CAPTURE_FILE" -n 2>/dev/null | wc -l | xargs || echo 0)
                SESSION_END=$(date -Iseconds)
                
                # Update Metadata
                jq --arg sid "$SESSION_ID" --arg cnt "$CONTAINER_NAME" \
                   --arg start "$SESSION_START" --arg end "$SESSION_END" \
                   --arg path "$CAPTURE_FILE" --argjson pc "$PACKET_COUNT" --argjson fs "$FILE_SIZE" \
                   '.sessions += [{session_id:$sid, container:$cnt, start_time:$start, end_time:$end, file_path:$path, packet_count:$pc, file_size:$fs}]' \
                   "$METADATA_FILE" > "${METADATA_FILE}.tmp" && mv "${METADATA_FILE}.tmp" "$METADATA_FILE"
                
                # Rotate Metadata (Keep last MAX_SESSIONS)
                jq --arg cnt "$CONTAINER_NAME" --argjson max "$MAX_SESSIONS" \
                   '.sessions = (.sessions | map(select(.container != $cnt))) + (.sessions | map(select(.container == $cnt)) | sort_by(.end_time) | reverse | .[0:$max])' \
                   "$METADATA_FILE" > "${METADATA_FILE}.tmp" && mv "${METADATA_FILE}.tmp" "$METADATA_FILE"
                
                # PHYSICAL DISK CLEANUP: Delete any .pcap file NOT in the metadata
                log "Cleaning up old disk captures..."
                TRACKED_FILES=$(jq -r '.sessions[].file_path' "$METADATA_FILE")
                for f in $OWNED_GLOB; do
                    if ! echo "$TRACKED_FILES" | grep -q "$(basename "$f")"; then
                        rm -f "$f"
                    fi
                done

                log "Saved: $PACKET_COUNT packets, $FILE_SIZE bytes"
            fi
            SESSION_ACTIVE=false
            CAPTURE_PID=0
        fi
        sleep 5
    fi
done