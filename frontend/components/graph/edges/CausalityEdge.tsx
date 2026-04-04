import React from 'react';
import { EdgeProps, getBezierPath } from '@xyflow/react';

/**
 * CausalityEdge - Represents causal relationships between nodes
 * Dotted 1.5px #f59e0b line with arrow markers at both ends
 * 
 * **Validates: Requirements 2.14**
 */
export function CausalityEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerStart,
  markerEnd,
}: EdgeProps) {
  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return (
    <>
      <path
        id={id}
        style={{
          ...style,
          stroke: '#f59e0b',
          strokeWidth: 1.5,
          strokeDasharray: '2 2',
        }}
        className="react-flow__edge-path"
        d={edgePath}
        markerStart={markerStart}
        markerEnd={markerEnd}
      />
    </>
  );
}
