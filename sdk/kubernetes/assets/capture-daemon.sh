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

# Generates a regex for conntrack to trigger on the correct ports
build_conntrack_regex() {
  # Turns "80:tcp,443:tcp" into "dport=(80|443)"
  local ports_only
  ports_only=$(echo "$PORTS" | sed 's/:tcp//g; s/:udp//g; s/,/|/g')
  echo "dport=($ports_only)"
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
CT_REGEX=$(build_conntrack_regex)

log "Starting session capture: Container=$CONTAINER_NAME, Ports=$PORTS"

SESSION_ACTIVE=false
LAST_ACTIVITY=$(date +%s)
LAST_FILE_SIZE=0
CAPTURE_PID=0
SESSION_ID=""
SESSION_START=""
CAPTURE_FILE=""

# Reporting function to update metadata
report_session() {
    if [ "$SESSION_ACTIVE" = false ] || [ ! -f "$CAPTURE_FILE" ]; then
        return
    fi
    
    # Ensure capture process is stopped
    if [ "$CAPTURE_PID" -ne 0 ] && kill -0 "$CAPTURE_PID" 2>/dev/null; then
        kill -TERM "$CAPTURE_PID" 2>/dev/null || true
        wait "$CAPTURE_PID" 2>/dev/null || true
    fi

    local packet_count
    packet_count=$(tcpdump -r "$CAPTURE_FILE" -n 2>/dev/null | wc -l | xargs || echo 0)

    if [ "$packet_count" -eq 0 ]; then
        log "Discarding empty session: ${SESSION_ID}"
        rm -f "$CAPTURE_FILE"
        return
    fi

    log "Updating metadata for session: ${SESSION_ID}"
    local file_size
    file_size=$(stat -c%s "$CAPTURE_FILE" 2>/dev/null || echo 0)
    local session_end
    session_end=$(date -Iseconds)
    local tmp_file="${METADATA_FILE}.tmp"
    jq --arg sid "$SESSION_ID" --arg cnt "$CONTAINER_NAME" \
        --arg start "$SESSION_START" --arg end "$session_end" \
        --arg path "$CAPTURE_FILE" --argjson pc "$packet_count" --argjson fs "$file_size" \
        '.sessions += [{session_id:$sid, container:$cnt, start_time:$start, end_time:$end, file_path:$path, packet_count:$pc, file_size:$fs}]' \
        "$METADATA_FILE" >"$tmp_file" && mv "$tmp_file" "$METADATA_FILE"

    jq --arg cnt "$CONTAINER_NAME" --argjson max "$MAX_SESSIONS" \
        '.sessions = (.sessions | map(select(.container != $cnt))) + (.sessions | map(select(.container == $cnt)) | sort_by(.end_time) | reverse | .[0:$max])' \
        "$METADATA_FILE" >"$tmp_file" && mv "$tmp_file" "$METADATA_FILE"

    local tracked_files
    tracked_files=$(jq -r '.sessions[].file_path' "$METADATA_FILE")
    for f in $OWNED_GLOB; do
        filename=$(basename "$f")
        if ! echo "$tracked_files" | grep -q "$filename"; then
            rm -f "$f"
        fi
    done
    log "Session reported: $packet_count packets, $file_size bytes"
}

cleanup() {
    log "Termination signal received, ensuring final sweep..."
    trap '' SIGTERM SIGINT # Prevent recursive calls
    report_session
    exit 0
}
trap cleanup SIGTERM SIGINT

exec 3< <(conntrack -E -e NEW -p tcp 2>/dev/null | grep --line-buffered -E "$CT_REGEX")

while true; do
  CURRENT_TIME=$(date +%s)

  if [ "$SESSION_ACTIVE" = false ]; then
    if read -u 3 -t 1 LINE; then
      SESSION_ID=$(cat /proc/sys/kernel/random/uuid)
      SESSION_START=$(date -Iseconds)

      CAPTURE_FILE="${CAPTURE_DIR}/${IDENTITY}-${CONTAINER_NAME}-${SESSION_ID}.pcap"
      [ -n "$LABEL" ] && CAPTURE_FILE="${CAPTURE_DIR}/${LABEL}-${IDENTITY}-${CONTAINER_NAME}-${SESSION_ID}.pcap"

      log "Kernel Event: NEW connection detected. Starting capture: ${SESSION_ID}"

      tcpdump -i eth0 -U -s "$MAX_CAPTURE_SIZE" -w "$CAPTURE_FILE" "$BPF_FILTER" &
      CAPTURE_PID=$!
      SESSION_ACTIVE=true
      LAST_ACTIVITY=$CURRENT_TIME
      LAST_FILE_SIZE=0
    fi
  else
    # Monitoring phase: check if the pcap is still growing
    if [ -f "$CAPTURE_FILE" ]; then
      CURRENT_FILE_SIZE=$(stat -c%s "$CAPTURE_FILE" 2>/dev/null || echo 0)
      if [ "$CURRENT_FILE_SIZE" -gt "$LAST_FILE_SIZE" ]; then
        LAST_ACTIVITY=$CURRENT_TIME
        LAST_FILE_SIZE=$CURRENT_FILE_SIZE
      fi
    fi

    # If no new data has been written for CONNECTION_TIMEOUT seconds, end session
    if [ $((CURRENT_TIME - LAST_ACTIVITY)) -ge "$CONNECTION_TIMEOUT" ]; then
      log "Inactivity timeout reached for session: ${SESSION_ID}"
      report_session
      # FLUSH BACKLOG: Clear the pipe so we don't immediately start a stale session
      while read -u 3 -t 0.1 DRAIN; do :; done
      SESSION_ACTIVE=false
      CAPTURE_PID=0
    fi
    sleep 1
  fi
done