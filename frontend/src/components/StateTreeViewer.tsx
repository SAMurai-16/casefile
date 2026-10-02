import React, { useState } from 'react';
import { Copy, Check, Braces } from 'lucide-react';

interface StateTreeViewerProps {
  stateValues: any;
}

export const StateTreeViewer: React.FC<StateTreeViewerProps> = ({ stateValues }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(stateValues, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm flex flex-col h-full">
      <div className="bg-slate-950 px-4 py-2.5 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Braces className="w-4 h-4 text-sky-400" />
          <h3 className="text-xs font-bold text-white uppercase tracking-wider">
            Full Checkpoint ClaimState (LangGraph)
          </h3>
        </div>

        <button
          onClick={handleCopy}
          className="flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs px-2.5 py-1 rounded border border-slate-700 transition"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          <span>{copied ? 'Copied!' : 'Copy JSON'}</span>
        </button>
      </div>

      <div className="flex-1 p-4 overflow-y-auto bg-slate-950/80 font-mono text-[11px] text-slate-300">
        {!stateValues || Object.keys(stateValues).length === 0 ? (
          <div className="text-center py-12 text-slate-500">No state snapshot available yet.</div>
        ) : (
          <pre className="whitespace-pre-wrap break-all leading-relaxed">
            {JSON.stringify(stateValues, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
};
