import React, { useState, useRef, useEffect } from 'react';
import { Send, LogOut, Loader, Database, FileText } from 'lucide-react';
import { chatApi } from '../services/api';
import MessageBubble from './MessageBubble';
import './ChatInterface.css';

export default function ChatInterface({ role, onLogout }) {
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      content: `Welcome to Fin Mind. You are authenticated as ${role}. How can I assist you today?`,
      type: 'text'
    }
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [queuedCount, setQueuedCount] = useState(0);

  const messagesEndRef = useRef(null);
  const isProcessingRef = useRef(false);
  const queueRef = useRef([]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping, queuedCount]);

  const processQuery = async (queryItem) => {
    isProcessingRef.current = true;
    setIsTyping(true);

    // Update message status to processing
    setMessages(prev => prev.map(m => m.id === queryItem.id ? { ...m, status: 'processing' } : m));

    try {
      const response = await chatApi.sendMessage(queryItem.content);
      
      // Handle SQL Agent specific formatting where the top-level keys are the data
      let content = response.answer || response.error;
      let data = response.data || null;
      
      if (response.metric) {
        content = `**${response.metric}** for ${response.ticker} (${response.year}): **${response.value}**\n\nFormula: \`${response.formula}\``;
      } else if (!content) {
        content = 'Request processed successfully.';
      }

      const assistantMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: content,
        data: data,
        route: response.route
      };
      
      setMessages(prev => [
        ...prev.map(m => m.id === queryItem.id ? { ...m, status: 'completed' } : m),
        assistantMessage
      ]);
    } catch (error) {
      console.error("Backend Error:", error);
      const errorMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: error.detail || error.error || error.message || 'Sorry, there is no data available.',
        isError: true
      };
      setMessages(prev => [
        ...prev.map(m => m.id === queryItem.id ? { ...m, status: 'error' } : m),
        errorMessage
      ]);
    } finally {
      // Process next queued question if any
      if (queueRef.current.length > 0) {
        const nextQuery = queueRef.current.shift();
        setQueuedCount(queueRef.current.length);
        await processQuery(nextQuery);
      } else {
        isProcessingRef.current = false;
        setIsTyping(false);
        setQueuedCount(0);
      }
    }
  };

  const handleSubmit = (e) => {
    if (e) e.preventDefault();
    const queryText = input.trim();
    if (!queryText) return;

    const isBusy = isProcessingRef.current;
    const userMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: queryText,
      status: isBusy ? 'queued' : 'processing'
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');

    if (isBusy) {
      queueRef.current.push(userMessage);
      setQueuedCount(queueRef.current.length);
    } else {
      processQuery(userMessage);
    }
  };

  return (
    <div className="chat-container">
      <header className="chat-header glass-panel">
        <div className="header-left">
          <h1>Fin Mind</h1>
          <span className={`role-badge role-${role.toLowerCase()}`}>{role}</span>
        </div>
        <button className="logout-btn" onClick={onLogout} title="Sign Out">
          <LogOut size={18} />
        </button>
      </header>

      <div className="chat-messages">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {isTyping && (
          <div className="message-wrapper assistant">
            <div className="message-bubble typing-bubble glass-panel">
              <Loader className="spinner" size={16} />
              <span>
                {queuedCount > 0 
                  ? `Synthesizing intelligence... (${queuedCount} queued)` 
                  : 'Synthesizing intelligence...'}
              </span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-area glass-panel">
        <form onSubmit={handleSubmit} className="input-form">
          <textarea
            placeholder={isTyping ? "Type next question (press Enter to queue)..." : "Ask about SEC filings, leverage ratios, or financial models..."}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
            autoFocus
            rows={1}
            style={{ resize: 'none', overflowY: 'auto', minHeight: '40px', maxHeight: '120px' }}
          />
          <button type="submit" className="send-btn" disabled={!input.trim()} title={isTyping ? "Queue question" : "Send question"}>
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
}

