import React from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';

interface IncidentNodeData {
  severity: 'critical' | 'warning';
}

export function IncidentNode({ data }: NodeProps<any>) {
  const { severity } = data as IncidentNodeData;

  // Background color based on severity
  const backgroundColor = severity === 'critical' ? '#ef4444' : '#f59e0b';

  return (
    <div
      style={{
        width: '60px',
        height: '52px',
        clipPath: 'polygon(50% 0%, 0% 100%, 100% 100%)',
        backgroundColor,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ top: '15%' }} />
      
      <div
        style={{
          fontSize: '24px',
          fontWeight: 700,
          color: 'white',
          marginTop: '8px',
        }}
      >
        !
      </div>

      <Handle type="source" position={Position.Bottom} style={{ bottom: '5%' }} />
    </div>
  );
}
