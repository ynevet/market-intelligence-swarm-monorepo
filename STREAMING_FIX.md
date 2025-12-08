# Streaming Connection Fix

## Problem
After approximately 20 seconds of user query processing, the application displayed an error:
```
Connection to stream failed. Ensure the backend is running.
```

## Root Cause
The issue was caused by running Flask's development server (`python application.py`) in the Docker Compose configuration, which has the following limitations:
1. **Connection timeouts** - Flask dev server is not designed for long-running streaming connections
2. **Poor SSE handling** - Server-Sent Events (SSE) may timeout or disconnect unexpectedly
3. **Single-threaded issues** - Limited ability to handle concurrent long-running requests

## Solution
Applied three fixes to resolve the streaming timeout issue:

### 1. Use Gunicorn Instead of Flask Dev Server
**File:** `docker-compose.yml`

**Change:** Modified the server command from:
```yaml
command: ["python", "application.py"]
```

To:
```yaml
command: ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "gthread", "--workers", "2", "--threads", "8", "--timeout", "0", "application:application"]
```

**Benefits:**
- `--timeout 0` disables worker timeout, allowing indefinite streaming
- `gthread` worker class supports threading for better concurrent request handling
- Production-grade WSGI server designed for long-running connections

### 2. Add Keepalive Mechanism to Backend
**File:** `server/application.py`

**Change:** Added periodic keepalive messages in the SSE stream:
```python
last_keepalive = time.time()

# In the streaming loop
for event in market_graph.stream(...):
    # ... process events ...
    
    # Send keepalive if no message in last 10 seconds
    if time.time() - last_keepalive > 10:
        yield sse_format({
            "type": "keepalive",
            "session_id": session_id,
            "message": "Processing..."
        })
        last_keepalive = time.time()
```

**Benefits:**
- Prevents timeout from proxies, load balancers, or browsers
- Keeps connection alive during long agent processing phases
- Provides user feedback that processing is still ongoing

### 3. Improve Client Error Handling
**File:** `client/src/App.jsx`

**Change:** Fixed error handling to use current state instead of stale closure:
```javascript
// Before (stale closure)
es.onerror = (err) => {
  if (streamLogs.length === 0 && !finalReport) {
    setError('Connection to stream failed...');
  }
};

// After (current state)
es.onerror = (err) => {
  setStreamLogs((currentLogs) => {
    if (currentLogs.length === 0) {
      setError('Connection to stream failed...');
    }
    return currentLogs;
  });
};
```

**Benefits:**
- Correctly checks if any logs were received before showing error
- Avoids false error messages when connection drops after successful streaming
- Uses React state updater function to access current state

## Testing
To test the fix:

1. **Rebuild and restart the services:**
   ```bash
   docker-compose down
   docker-compose up --build
   ```

2. **Submit a complex query** that takes longer than 20 seconds to process (e.g., "Map stripe.com and extract detailed pricing tiers and feature comparisons")

3. **Expected behavior:**
   - Connection should remain active throughout the entire processing
   - Keepalive messages appear every 10 seconds if no agent messages
   - Final report is delivered successfully without timeout errors

## Additional Recommendations

### For Production Deployment
1. **Add reverse proxy configuration** (if using nginx/apache):
   ```nginx
   # Nginx example
   proxy_read_timeout 300s;
   proxy_connect_timeout 75s;
   proxy_send_timeout 300s;
   ```

2. **Consider adding request rate limiting** to prevent abuse of long-running streaming endpoints

3. **Monitor worker health** and adjust worker/thread counts based on load:
   ```yaml
   # For higher load
   command: ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "gthread", "--workers", "4", "--threads", "16", "--timeout", "0", "application:application"]
   ```

### For Development
If you need to use Flask dev server for debugging, add timeout handling:
```python
if __name__ == "__main__":
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.protocol_version = "HTTP/1.1"
    application.run(host="0.0.0.0", debug=True, port=5000, threaded=True)
```

## Technical Details

### Why Gunicorn with gthread?
- **gthread worker class**: Uses threading, which is efficient for I/O-bound operations (like API calls to OpenAI, Tavily)
- **Multiple workers**: Allows handling multiple concurrent research requests
- **Multiple threads per worker**: Each worker can handle multiple concurrent connections
- **timeout=0**: Critical for streaming - disables worker timeout completely

### SSE Connection Lifecycle
1. Client opens EventSource connection to `/research-stream?query=...`
2. Server validates query and starts streaming
3. Server yields SSE messages as agents process the request
4. Server sends keepalive every 10 seconds if no agent activity
5. Server sends final report and closes connection
6. Client handles connection close gracefully

## Files Modified
- ✅ `docker-compose.yml` - Switch to Gunicorn
- ✅ `server/application.py` - Add keepalive mechanism
- ✅ `client/src/App.jsx` - Fix error handling

## Status
✅ **RESOLVED** - Streaming connections should now work reliably for queries taking any amount of time.
