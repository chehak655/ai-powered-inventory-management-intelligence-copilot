import React, { useState, useEffect, useRef } from 'react';
import { copilotApi } from '../services/api';
import { CopilotResponse } from '../types';
import {
  Bot,
  Send,
  Sparkles,
  User as UserIcon,
  Database,
  Cpu,
  Boxes,
  Loader2,
  RefreshCw,
  Lightbulb,
} from 'lucide-react';

interface ChatMessage {
  id: string;
  sender: 'user' | 'copilot';
  text: string;
  groundedSources?: string[];
  engine?: string;
  timestamp: Date;
}

export const CopilotPage: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      sender: 'copilot',
      text: "👋 Welcome to **AI Powered Inventory Management and Intelligence Copilot**! I am grounded in your company's real datasets, trained machine learning models, and inventory health metrics. Ask me anything about stockout vulnerabilities, champion model performance, or replenishment schedules.",
      groundedSources: ['Company Workspace Data'],
      engine: 'Grounded Intelligence Copilot',
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [suggestedPrompts, setSuggestedPrompts] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    copilotApi.getPrompts().then((prompts) => {
      setSuggestedPrompts(prompts);
    });
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async (promptText?: string) => {
    const textToSend = promptText || input;
    if (!textToSend.trim() || loading) return;

    const userMsg: ChatMessage = {
      id: String(Date.now()),
      sender: 'user',
      text: textToSend,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!promptText) setInput('');
    setLoading(true);

    try {
      const res: CopilotResponse = await copilotApi.query(textToSend);
      const botMsg: ChatMessage = {
        id: String(Date.now() + 1),
        sender: 'copilot',
        text: res.answer,
        groundedSources: res.grounded_sources,
        engine: res.model_engine,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: String(Date.now() + 1),
        sender: 'copilot',
        text: `⚠️ Apologies, I encountered an issue analyzing your workspace data: ${
          err.response?.data?.detail || err.message
        }`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-[calc(100vh-6.5rem)] flex flex-col bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-slate-900/50">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-600 dark:bg-indigo-500 text-white flex items-center justify-center shadow-xs">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-1.5">
              <span>AI Powered Inventory Intelligence Copilot</span>
              <span className="px-1.5 py-0.2 bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 text-[10px] font-extrabold uppercase rounded">
                Grounded
              </span>
            </h2>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              Conversational intelligence grounded in your company's datasets, candidate models, and inventory health.
            </p>
          </div>
        </div>

        <button
          onClick={() =>
            setMessages([
              {
                id: 'welcome',
                sender: 'copilot',
                text: "👋 Session reset! I am ready to analyze your inventory data, forecasting models, and purchase orders.",
                timestamp: new Date(),
              },
            ])
          }
          className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title="Reset conversation"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-5 bg-gradient-to-b from-slate-50/30 to-white dark:from-slate-900/40 dark:to-slate-950">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex items-start space-x-3 ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.sender === 'copilot' && (
              <div className="w-8 h-8 rounded-lg bg-indigo-100 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 flex items-center justify-center flex-shrink-0 mt-0.5">
                <Bot className="w-4 h-4" />
              </div>
            )}

            <div
              className={`max-w-2xl rounded-2xl p-4 text-xs leading-relaxed ${
                msg.sender === 'user'
                  ? 'bg-slate-900 dark:bg-slate-800 text-white shadow-sm rounded-br-xs'
                  : 'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200 shadow-2xs rounded-bl-xs'
              }`}
            >
              {/* Message Content formatted with linebreaks and bold */}
              <div className="whitespace-pre-line font-normal space-y-1">
                {msg.text.split('\n').map((line, idx) => {
                  if (line.startsWith('### ')) {
                    return (
                      <h4 key={idx} className="font-bold text-sm text-slate-900 dark:text-slate-100 mt-2 mb-1">
                        {line.replace('### ', '')}
                      </h4>
                    );
                  }
                  if (line.startsWith('- **')) {
                    const match = line.match(/- \*\*(.*?)\*\*(.*)/);
                    if (match) {
                      return (
                        <div key={idx} className="ml-2 flex items-start space-x-1.5">
                          <span className="text-brand-600 dark:text-brand-400 font-bold">•</span>
                          <span>
                            <strong>{match[1]}</strong>
                            {match[2]}
                          </span>
                        </div>
                      );
                    }
                  }
                  return <p key={idx}>{line}</p>;
                })}
              </div>

              {/* Grounded Sources & Engine Footer */}
              {msg.groundedSources && msg.groundedSources.length > 0 && (
                <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-800 flex flex-wrap items-center gap-1.5 text-[10px]">
                  <span className="text-slate-400 dark:text-slate-500 font-bold uppercase">Grounded Context:</span>
                  {msg.groundedSources.map((source, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-semibold"
                    >
                      <Database className="w-2.5 h-2.5 text-slate-400" />
                      <span>{source}</span>
                    </span>
                  ))}
                  {msg.engine && (
                    <span className="ml-auto text-slate-400 dark:text-slate-500 italic text-[9px]">{msg.engine}</span>
                  )}
                </div>
              )}
            </div>

            {msg.sender === 'user' && (
              <div className="w-8 h-8 rounded-lg bg-slate-800 dark:bg-slate-700 text-slate-200 flex items-center justify-center flex-shrink-0 mt-0.5">
                <UserIcon className="w-4 h-4" />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex items-start space-x-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-100 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Bot className="w-4 h-4" />
            </div>
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 text-xs text-slate-500 dark:text-slate-400 shadow-2xs flex items-center space-x-2">
              <Loader2 className="w-4 h-4 text-brand-600 dark:text-brand-400 animate-spin" />
              <span>Analyzing live tenant datasets and inventory models...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Prompt Chips */}
      {suggestedPrompts.length > 0 && (
        <div className="px-6 py-2.5 bg-slate-50 dark:bg-slate-900/80 border-t border-slate-100 dark:border-slate-800 flex items-center space-x-2 overflow-x-auto">
          <Lightbulb className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
          <div className="flex items-center space-x-2 whitespace-nowrap">
            {suggestedPrompts.map((prompt, i) => (
              <button
                key={i}
                type="button"
                onClick={() => handleSend(prompt)}
                disabled={loading}
                className="px-2.5 py-1 bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-lg text-[11px] text-slate-700 dark:text-slate-300 font-medium transition-colors cursor-pointer"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Form */}
      <form onSubmit={(e) => { e.preventDefault(); handleSend(); }} className="p-4 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 flex items-center space-x-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question (e.g. Which SKUs need reordering? What is our best ML model?)..."
          disabled={loading}
          className="flex-1 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:bg-white dark:focus:bg-slate-900 focus:ring-brand-500 focus:border-brand-500"
        />
        <button
          type="submit"
          disabled={!input.trim() || loading}
          className="inline-flex items-center justify-center w-10 h-10 bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-600 dark:hover:bg-indigo-500 text-white rounded-xl transition-all shadow-sm disabled:opacity-50"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
};
