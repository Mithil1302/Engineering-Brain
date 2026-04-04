import React from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';

interface APINodeData {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  path: string;
}

export function APINode({ data }: NodeProps<any>) {
  const { method, path } = data as APINodeData;

  // Method colors
  const methodColors: Record<string, string> = {
    GET: '#3b82f6',    // blue
    POST: '#22c55e',   // green
    PUT: '#f59e0b',    // amber
    DELETE: '#ef4444', // red
    PATCH: '#a855f7',  // purple
  };

  const methodColor = methodColors[method] || '#6b7280';

  return (
    <div
      style={{
        minWidth: '100px',
        maxWidth: '160px',
        height: '28px',
        borderRadius: '14px',
        backgroundColor: '#f3f4f6',
        display: 'flex',
        alignItems: 'center',
        overflow: 'hidden',
      }}
    >
      <Handle type="target" position={Position.Left} />
      
      <div
        style={{
          backgroundColor: methodColor,
          color: 'white',
          fontSize: '9px',
          fontWeight: 700,
          padding: '0 8px',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minWidth: '40px',
        }}
      >
        {method}
      </div>

      <div
        style={{
          fontSize: '11px',
          fontFamily: 'monospace',
          color: '#1f2937',
          padding: '0 8px',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          flex: 1,
        }}
      >
        {path}
      </div>

      <Handle type="source" position={Position.Right} />
    </div>
  );
}
