#!/bin/bash
# Session-based packet capture daemon
# Monitors connections and creates individual pcap files per session
# Maintains max 3 capture files per container, rotating by end time

set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-unknown}"
IDENTITY="${IDENTITY:-unknown}"
LABEL="${LABEL:-}"
CAPTURE_DIR="${CAPTURE_DIR:-/captures}"
PORTS="${PORTS:-}"  # Comma-separated list of port:protocol pairs (e.g., "8080:tcp,53:udp")
MAX_SESSIONS=3
METADATA_FILE="${CAPTURE_DIR}/sessions.json"
CONNECTION_TIMEOUT=300  # 5 minutes of inactivity = disconnection

# Ensure capture directory exists
mkdir -p "${CAPTURE_DIR}"

# Initialize metadata if it doesn't exist
if [ ! -f "${METADATA_FILE}" ]; then
    echo '{"sessions":[]}' > "${METADATA_FILE}"
fi

# Parse ports and build BPF filter
build_filter() {
    local filter=""
    IFS=',' read -ra PORT_ARRAY <<< "$PORTS"
    for port_proto in "${PORT_ARRAY[@]}"; do
        IFS=':' read -r port proto <<< "$port_proto"
        proto="${proto:-tcp}"
        if [ -n "$filter" ]; then
            filter="$filter or "
        fi
        filter="$filter(${proto} port ${port})"
    done
    echo "$filter"
}

BPF_FILTER=$(build_filter)

log() {
    echo "[$(date -Iseconds)] $*" >&2
}

# Get active connections count
get_connection_count() {
    local filter="$1"
    # Use ss to count active connections on monitored ports
    local count=0
    IFS=',' read -ra PORT_ARRAY <<< "$PORTS"
    for port_proto in "${PORT_ARRAY[@]}"; do
        IFS=':' read -r port proto <<< "$port_proto"
        local current=$(ss -tan | grep ":${port}" | grep ESTAB | wc -l)
        count=$((count + current))
    done
    echo "$count"
}

# Rotate sessions - keep only the 3 most recent by end_time
rotate_sessions() {
    local container="$1"
    
    # Read current sessions
    local sessions=$(jq -r --arg container "$container" \
        '.sessions | map(select(.container == $container)) | sort_by(.end_time) | reverse' \
        "${METADATA_FILE}")
    
    local count=$(echo "$sessions" | jq 'length')
    
    if [ "$count" -gt "$MAX_SESSIONS" ]; then
        log "Rotating captures for ${container}: ${count} > ${MAX_SESSIONS}"
        
        # Get sessions to delete (oldest ones)
        local to_delete=$(echo "$sessions" | jq -r ".[$MAX_SESSIONS:] | .[] | .file_path")
        
        # Delete old capture files
        for file in $to_delete; do
            if [ -f "$file" ]; then
                log "Deleting old capture: $file"
                rm -f "$file"
            fi
        done
        
        # Update metadata - keep only MAX_SESSIONS most recent
        jq --arg container "$container" --argjson max "$MAX_SESSIONS" \
            '.sessions = (
                (.sessions | map(select(.container != $container))) +
                (.sessions | map(select(.container == $container)) | sort_by(.end_time) | reverse | .[:$max])
            )' \
            "${METADATA_FILE}" > "${METADATA_FILE}.tmp"
        mv "${METADATA_FILE}.tmp" "${METADATA_FILE}"
    fi
}

# Add session to metadata
add_session() {
    local session_id="$1"
    local start_time="$2"
    local end_time="$3"
    local file_path="$4"
    local packet_count="$5"
    local file_size="$6"
    
    jq --arg sid "$session_id" \
       --arg container "$CONTAINER_NAME" \
       --arg start "$start_time" \
       --arg end "$end_time" \
       --arg path "$file_path" \
       --argjson packets "$packet_count" \
       --argjson size "$file_size" \
       '.sessions += [{
           session_id: $sid,
           container: $container,
           start_time: $start,
           end_time: $end,
           file_path: $path,
           packet_count: $packets,
           file_size: $size
       }]' \
       "${METADATA_FILE}" > "${METADATA_FILE}.tmp"
    mv "${METADATA_FILE}.tmp" "${METADATA_FILE}"
    
    # Rotate if needed
    rotate_sessions "$CONTAINER_NAME"
}

# Main capture loop
log "Starting session-based packet capture daemon"
log "Container: ${CONTAINER_NAME}"
log "Identity: ${IDENTITY}"
log "Ports: ${PORTS}"
log "BPF Filter: ${BPF_FILTER}"
log "Max sessions: ${MAX_SESSIONS}"

SESSION_ACTIVE=false
SESSION_ID=""
SESSION_START=""
CAPTURE_PID=""
CAPTURE_FILE=""
LAST_ACTIVITY=$(date +%s)

while true; do
    CONNECTION_COUNT=$(get_connection_count "$BPF_FILTER")
    CURRENT_TIME=$(date +%s)
    
    if [ "$CONNECTION_COUNT" -gt 0 ]; then
        LAST_ACTIVITY=$CURRENT_TIME
        
        if [ "$SESSION_ACTIVE" = false ]; then
            # New session detected
            SESSION_ID=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid)
            SESSION_START=$(date -Iseconds)
            
            if [ -n "$LABEL" ]; then
                CAPTURE_FILE="${CAPTURE_DIR}/${LABEL}-${IDENTITY}-${CONTAINER_NAME}-${SESSION_ID}.pcap"
            else
                CAPTURE_FILE="${CAPTURE_DIR}/${IDENTITY}-${CONTAINER_NAME}-${SESSION_ID}.pcap"
            fi
            
            log "New session detected: ${SESSION_ID}"
            log "Starting capture to: ${CAPTURE_FILE}"
            
            # Start tcpdump in background
            tcpdump -i any -s 96 -w "$CAPTURE_FILE" "$BPF_FILTER" 2>&1 | \
                while IFS= read -r line; do
                    echo "[$(date -Iseconds)] [tcpdump] $line"
                done &
            CAPTURE_PID=$!
            
            SESSION_ACTIVE=true
        fi
    else
        # No active connections
        if [ "$SESSION_ACTIVE" = true ]; then
            # Check if session timed out
            local inactive_duration=$((CURRENT_TIME - LAST_ACTIVITY))
            
            if [ "$inactive_duration" -ge "$CONNECTION_TIMEOUT" ]; then
                # Session ended
                SESSION_END=$(date -Iseconds)
                log "Session ended: ${SESSION_ID}"
                log "Duration: ${inactive_duration}s"
                
                # Stop tcpdump
                if [ -n "$CAPTURE_PID" ] && kill -0 "$CAPTURE_PID" 2>/dev/null; then
                    kill -TERM "$CAPTURE_PID" 2>/dev/null || true
                    wait "$CAPTURE_PID" 2>/dev/null || true
                fi
                
                # Get capture file stats
                if [ -f "$CAPTURE_FILE" ]; then
                    FILE_SIZE=$(stat -f%z "$CAPTURE_FILE" 2>/dev/null || stat -c%s "$CAPTURE_FILE")
                    PACKET_COUNT=$(tcpdump -r "$CAPTURE_FILE" -q 2>/dev/null | wc -l || echo "0")
                    
                    log "Capture complete: ${PACKET_COUNT} packets, ${FILE_SIZE} bytes"
                    
                    # Add to metadata
                    add_session "$SESSION_ID" "$SESSION_START" "$SESSION_END" "$CAPTURE_FILE" "$PACKET_COUNT" "$FILE_SIZE"
                else
                    log "Warning: Capture file not found: ${CAPTURE_FILE}"
                fi
                
                SESSION_ACTIVE=false
                SESSION_ID=""
                CAPTURE_PID=""
                CAPTURE_FILE=""
            fi
        fi
    fi
    
    # Check every 5 seconds
    sleep 5
done
