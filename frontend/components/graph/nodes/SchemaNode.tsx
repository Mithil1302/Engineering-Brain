import React from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';

interface SchemaNodeData {
  label: string;
}

export function SchemaNode({ data }: NodeProps<any>) {
  const { label } = data as SchemaNodeData;

  return (
    <div
      style={{
        width: '80px',
        height: '80px',
        transform: 'rotate(45deg)',
        backgroundColor: '#8b5cf6',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ transform: 'rotate(-45deg)' }} />
      
      <div
        style={{
          transform: 'rotate(-45deg)',
          fontSize: '11px',
          color: 'white',
          fontWeight: 600,
          textAlign: 'center',
          maxWidth: '60px',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </div>

      <Handle type="source" position={Position.Bottom} style={{ transform: 'rotate(-45deg)' }} />
    </div>
  );
}
