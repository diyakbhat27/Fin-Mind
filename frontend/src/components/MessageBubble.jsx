import React, { useMemo } from 'react';
import { Database, FileText, AlertCircle, BookOpen, Layers } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './MessageBubble.css';

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  
  // Extract unique sources and format content for markdown
  const { markdownText, sources } = useMemo(() => {
    if (!message.content || isUser) return { markdownText: message.content, sources: [] };
    
    let text = message.content;
    const uniqueSources = [];
    const sourceMap = new Map();
    
    // Extract citations and replace with markdown links
    text = text.replace(/(<citation>.*?<\/citation>)/g, (match) => {
      const citationText = match.replace(/<\/?citation>/g, '').trim();
      let sourceNum = sourceMap.get(citationText);
      if (!sourceNum) {
        sourceNum = uniqueSources.length + 1;
        sourceMap.set(citationText, sourceNum);
        uniqueSources.push({ id: sourceNum, text: citationText });
      }
      return `[${sourceNum}](#citation-${sourceNum})`;
    });
    
    return { markdownText: text, sources: uniqueSources };
  }, [message.content, isUser]);

  return (
    <div className={`message-wrapper ${isUser ? 'user' : 'assistant'} animate-fade-in`}>
      <div className={`message-bubble ${isUser ? 'user-bubble' : 'assistant-bubble glass-panel'} ${message.isError ? 'error-bubble' : ''}`}>
        
        {/* Reasoning Step / Route Indicator */}
        {!isUser && message.route && (
          <div className="reasoning-step">
            {message.route === 'sql_agent' ? (
              <><Database size={14} /> <span>Quantitative Engine • Executed AST query</span></>
            ) : (
              <><Layers size={14} /> <span>RAG Search • Scanned SEC filings</span></>
            )}
          </div>
        )}

        {/* Sources Block (Perplexity Style) */}
        {!isUser && sources.length > 0 && (
          <div className="sources-block">
            <div className="sources-header">
              <BookOpen size={14} /> <span>Sources</span>
            </div>
            <div className="sources-grid">
              {sources.map(src => (
                <div key={src.id} className="source-chip" title={src.text}>
                  <span className="source-number">{src.id}</span>
                  <span className="source-text">{src.text.substring(0, 30)}{src.text.length > 30 ? '...' : ''}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Render Error Icon */}
        {message.isError && (
          <div className="error-header">
            <AlertCircle size={16} /> <span>Access Denied / Error</span>
          </div>
        )}

        {/* Render Content */}
        <div className="message-content markdown-body">
          {isUser ? (
            <>
              <div>{message.content}</div>
              {message.status === 'queued' && (
                <div className="queued-status">
                  <span className="pulse-dot" />
                  <span>Queued • Waiting for previous response</span>
                </div>
              )}
            </>
          ) : (
            <ReactMarkdown 
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({node, ...props}) => {
                  if (props.href && props.href.startsWith('#citation-')) {
                    const citationNum = props.href.replace('#citation-', '');
                    const src = sources.find(s => s.id.toString() === citationNum);
                    return <span className="inline-citation" title={src ? src.text : ''}>[{props.children}]</span>
                  }
                  return <a {...props} target="_blank" rel="noopener noreferrer" />
                }
              }}
            >
              {markdownText}
            </ReactMarkdown>
          )}
        </div>

        {/* Render Structured Data if present (from SQL Agent) */}
        {!isUser && message.data && (
          <div className="structured-data-container">
            <div className="data-table">
              {message.data.map((row, i) => (
                <div key={i} className="data-row">
                  {Object.entries(row).map(([key, val]) => (
                    <div key={key} className="data-cell">
                      <span className="data-key">{key}</span>
                      <span className="data-val">{val}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
