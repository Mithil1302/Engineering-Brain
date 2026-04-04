import React from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';

interface EngineerNodeData {
  name: string;
}

export function EngineerNode({ data }: NodeProps<any>) {
  const { name } = data as EngineerNodeData;

  // 8 predefined colors
  const colors = [
    '#ef4444', // red
    '#f59e0b', // amber
    '#22c55e', // green
    '#3b82f6', // blue
    '#8b5cf6', // purple
    '#ec4899', // pink
    '#06b6d4', // cyan
    '#f97316', // orange
  ];

  // Hash function to deterministically select color
  const hashString = (str: string): number => {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return Math.abs(hash);
  };

  const colorIndex = hashString(name) % colors.length;
  const backgroundColor = colors[colorIndex];

  // Extract initials (first letter of first and last name)
  const getInitials = (fullName: string): string => {
    const parts = fullName.trim().split(/\s+/);
    if (parts.length === 1) {
      return parts[0].charAt(0).toUpperCase();
    }
    return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
  };

  const initials = getInitials(name);

  return (
    <div
      style={{
        width: '52px',
        height: '52px',
        borderRadius: '50%',
        backgroundColor,
        border: '2px solid white',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Handle type="target" position={Position.Top} />
      
      <div
        style={{
          fontSize: '16px',
          fontWeight: 700,
          color: 'white',
          userSelect: 'none',
        }}
      >
        {initials}
      </div>

      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
