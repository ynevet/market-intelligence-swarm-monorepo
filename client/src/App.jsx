import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Search, Loader2, AlertCircle, StopCircle, Terminal, FileText } from 'lucide-react';

const SERVER_BASE_URL = import.meta.env.VITE_SERVER_URL || 'http://127.0.0.1:5000';

export default function AIResearchApp() {
  const [query, setQuery] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [finalReport, setFinalReport] = useState(null);
  const [streamLogs, setStreamLogs] = useState([]);
  const [error, setError] = useState(null);
  const [sessionId, setSessionId] = useState(null);

  const eventSourceRef = useRef(null);
  const logsEndRef = useRef(null);

  const appendLog = useCallback((entry) => {
    setStreamLogs((prev) => [
      ...prev,
      {
        ...entry,
        timestamp: entry.timestamp || new Date().toISOString(),
      },
    ]);
  }, []);

  const parseMarkdown = (text) => {
    if (!text) return '';
    let html = text
      .replace(/^#### (.*$)/gim, '<h4 class="text-lg font-semibold mt-4 mb-2 text-gray-900">$1</h4>')
      .replace(/^### (.*$)/gim, '<h3 class="text-xl font-semibold mt-6 mb-3 text-gray-900">$1</h3>')
      .replace(/^## (.*$)/gim, '<h2 class="text-2xl font-semibold mt-6 mb-3 text-gray-900">$1</h2>')
      .replace(/^# (.*$)/gim, '<h1 class="text-3xl font-bold mt-6 mb-4 text-gray-900">$1</h1>')
      .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-900">$1</strong>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:text-blue-800 underline">$1</a>')
      .replace(/\n\n/g, '</p><p class="mb-3">')
      .replace(/\n/g, '<br/>');
    return `<p class="mb-3">${html}</p>`;
  };

  const handleStartStream = async () => {
    if (!query.trim()) return;

    setIsStreaming(true);
    setError(null);
    setFinalReport(null);
    setStreamLogs([]);
    setSessionId(null);

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    try {
      const url = `${SERVER_BASE_URL}/research-stream?query=${encodeURIComponent(query)}`;
      const es = new EventSource(url);
      eventSourceRef.current = es;

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.session_id) {
            setSessionId(data.session_id);
          }

          if (data.type === 'error') {
            setError(data.message || 'An error occurred during processing');
            es.close();
            setIsStreaming(false);
          } else if (['agent_message', 'progress', 'status'].includes(data.type)) {
            appendLog(data);
          } else if (data.type === 'final') {
            setFinalReport(data.message);
            es.close();
            setIsStreaming(false);
          }
        } catch (err) {
          console.error("Error parsing JSON stream:", err);
        }
      };

      es.onerror = (err) => {
        console.error("Stream error:", err);
        if (streamLogs.length === 0 && !finalReport) {
            setError('Connection to stream failed. Ensure the backend is running.');
        }
        es.close();
        setIsStreaming(false);
      };

    } catch (err) {
      setError(err.message);
      setIsStreaming(false);
    }
  };

  const handleStopStream = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      appendLog({ type: 'info', message: 'Stream stopped by user.' });
      setIsStreaming(false);
    }
  };

  const handleDownloadReport = () => {
    if (!finalReport) return;
    const blob = new Blob([finalReport], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const filename = `market-intel-report-${sessionId || 'latest'}.md`;
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    appendLog({ type: 'info', message: `Report exported as ${filename}` });
  };

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [streamLogs]);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 p-4 sm:p-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-8 px-2">
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-2 leading-tight">Market Intelligence Swarm</h1>
          <p className="text-sm sm:text-base text-gray-600">Real-time AI competitive analysis stream</p>
        </div>

        <div className="mb-8">
          <div className="bg-white rounded-lg shadow-md p-4 sm:p-6">
            <div className="flex flex-col sm:flex-row gap-3">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && !isStreaming && handleStartStream()}
                placeholder="e.g., Map stripe.com and extract pricing tiers"
                className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent w-full"
                disabled={isStreaming}
              />
              
              {isStreaming ? (
                 <button
                 onClick={handleStopStream}
                 className="w-full sm:w-auto px-6 py-3 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors flex items-center justify-center gap-2 font-medium"
               >
                 <StopCircle className="w-5 h-5" />
                 Stop
               </button>
              ) : (
                <button
                  onClick={handleStartStream}
                  disabled={!query.trim()}
                  className="w-full sm:w-auto px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 font-medium"
                >
                  <Search className="w-5 h-5" />
                  Analyze
                </button>
              )}
            </div>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6 flex items-start gap-3 text-sm sm:text-base">
            <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5 hidden sm:block" />
            <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5 sm:hidden" />
            <div>
              <h3 className="font-semibold text-red-900 mb-1">Error</h3>
              <p className="text-red-700">{error}</p>
            </div>
          </div>
        )}

        <div className="grid gap-6">
            
            {(streamLogs.length > 0 || isStreaming) && (
                <div className="bg-gray-900 rounded-lg shadow-md p-4 sm:p-6 text-gray-300 font-mono text-xs sm:text-sm border border-gray-700">
                    <div className="flex flex-wrap items-center gap-2 mb-4 border-b border-gray-700 pb-2">
                        <Terminal className="w-4 h-4 text-green-400" />
                        <span className="font-semibold text-gray-100 text-sm sm:text-base">Live Agent Activity</span>
                        {isStreaming && <Loader2 className="w-3 h-3 animate-spin text-green-400 ml-auto" />}
                    </div>
                    <div className="max-h-64 sm:max-h-60 overflow-y-auto space-y-2 pr-2">
                         {streamLogs.map((log, idx) => (
                             <div key={idx} className="flex gap-3 animate-in fade-in slide-in-from-bottom-1 duration-300">
                                 <span className="text-blue-400 shrink-0">[{new Date(log.timestamp || Date.now()).toLocaleTimeString()}]</span>
                                <span className={log.type === 'error' ? 'text-red-400' : 'text-gray-300'}>
                                    {log.node ? `[${log.node}] ` : ''}{log.message}
                                </span>
                            </div>
                        ))}
                        {isStreaming && (
                            <div className="animate-pulse text-green-500">_</div>
                        )}
                        <div ref={logsEndRef} />
                    </div>
                </div>
            )}

            {finalReport && (
            <div className="bg-white rounded-lg shadow-md p-5 sm:p-8 border-t-4 border-blue-600 animate-in fade-in zoom-in duration-500">
                <div className="mb-4 pb-4 border-b border-gray-200 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-2">
                        <FileText className="w-6 h-6 text-blue-600" />
                        <h2 className="text-xl sm:text-2xl font-bold text-gray-900">Final Report</h2>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                        {sessionId && (
                            <span className="text-xs font-mono bg-gray-100 px-2 py-1 rounded text-gray-500">ID: {sessionId}</span>
                        )}
                        <button
                          onClick={handleDownloadReport}
                          className="w-full sm:w-auto px-3 py-2 text-sm font-medium text-blue-700 border border-blue-200 rounded-md hover:bg-blue-50 transition-colors text-center"
                        >
                          Export Markdown
                        </button>
                    </div>
                </div>
                <div 
                className="prose prose-sm max-w-none text-gray-700 [&_h1]:text-gray-900 [&_h2]:text-gray-900 [&_h3]:text-gray-900 [&_h4]:text-gray-900 [&_h5]:text-gray-900 [&_h6]:text-gray-900 [&_strong]:text-gray-900"
                dangerouslySetInnerHTML={{ __html: parseMarkdown(finalReport) }}
                />
            </div>
            )}

            {!finalReport && streamLogs.length === 0 && !error && !isStreaming && (
            <div className="bg-white rounded-lg shadow-md p-8 sm:p-12 text-center">
                <Search className="w-12 h-12 sm:w-16 sm:h-16 text-gray-300 mx-auto mb-4" />
                <h3 className="text-lg sm:text-xl font-semibold text-gray-700 mb-2">Ready to analyze competitors</h3>
                <p className="text-sm sm:text-base text-gray-500">Enter a market research question to stream real-time insights</p>
                
                <div className="mt-6 text-left max-w-md mx-auto bg-gray-50 rounded-lg p-4">
                    <p className="text-sm font-semibold text-gray-700 mb-2">Example queries:</p>
                    <ul className="text-sm text-gray-600 space-y-1">
                        <li>• Map stripe.com and extract pricing tiers</li>
                        <li>• Analyze hubspot.com product features</li>
                        <li>• Benchmark Cursor AI vs GitHub Copilot for enterprise teams</li>
                        <li>• Compare Spotify’s pricing and feature bundles against Apple Music</li>
                    </ul>
                </div>
            </div>
            )}
        </div>
      </div>
    </div>
  );
}