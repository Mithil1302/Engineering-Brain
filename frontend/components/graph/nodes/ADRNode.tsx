import React from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';

interface ADRNodeData {
  adr_number: number;
  title: string;
}

export function ADRNode({ data }: NodeProps<any>) {
  const { adr_number, title } = data as ADRNodeData;

  // Truncate title to 20 characters
  const truncatedTitle = title.length > 20 ? title.substring(0, 20) + '...' : title;

  return (
    <div
      className="relative"
      style={{
        width: '100px',
        height: '64px',
        backgroundColor: '#fbbf24',
        padding: '8px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        position: 'relative',
      }}
    >
      <Handle type="target" position={Position.Left} />
      
      {/* Folded corner using ::before pseudo-element */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          right: 0,
          width: 0,
          height: 0,
          borderStyle: 'solid',
          borderWidth: '0 12px 12px 0',
          borderColor: 'transparent #f59e0b transparent transparent',
        }}
      />

      <div
        style={{
          fontSize: '12px',
          fontWeight: 700,
          color: '#1f2937',
          lineHeight: '1.2',
        }}
      >
        ADR-{adr_number}
      </div>

      <div
        style={{
          fontSize: '10px',
          color: '#1f2937',
          lineHeight: '1.2',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
        }}
      >
        {truncatedTitle}
      </div>

      <Handle type="source" position={Position.Right} />
    </div>
  );
}
