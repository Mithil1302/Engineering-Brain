import React from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';

interface ServiceNodeData {
  service_name: string;
  owner_name?: string;
  health_score: number;
}

export function ServiceNode({ data }: NodeProps<any>) {
  const { service_name, owner_name, health_score } = data as ServiceNodeData;

  // Health_Color_Scale: 0-40=red, 40-60=amber, 60-100=green
  const getHealthColor = (score: number): string => {
    if (score < 40) return '#ef4444'; // red
    if (score < 60) return '#f59e0b'; // amber
    return '#22c55e'; // green
  };

  const backgroundColor = getHealthColor(health_score);
  const shouldPulse = health_score < 40;

  return (
    <div
      className="relative"
      style={{
        width: '180px',
        height: '72px',
        borderRadius: '8px',
        backgroundColor,
        padding: '8px 12px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        animation: shouldPulse ? 'pulse-shadow 2s ease-in-out infinite' : 'none',
      }}
    >
      <Handle type="target" position={Position.Top} />
      
      <div className="flex flex-col">
        <div
          style={{
            fontSize: '13px',
            fontWeight: 700,
            color: 'white',
            lineHeight: '1.2',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {service_name}
        </div>
        {owner_name && (
          <div
            style={{
              fontSize: '11px',
              color: 'white',
              opacity: 0.7,
              lineHeight: '1.2',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {owner_name}
          </div>
        )}
      </div>

      <div
        style={{
          position: 'absolute',
          top: '8px',
          right: '8px',
          width: '22px',
          height: '22px',
          borderRadius: '4px',
          backgroundColor: 'white',
          color: backgroundColor,
          fontSize: '11px',
          fontWeight: 700,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {health_score}
      </div>

      <Handle type="source" position={Position.Bottom} />

      <style jsx>{`
        @keyframes pulse-shadow {
          0%, 100% {
            box-shadow: 0 0 0 0 ${backgroundColor}00;
          }
          50% {
            box-shadow: 0 0 0 6px ${backgroundColor}40;
          }
        }
      `}</style>
    </div>
  );
}
