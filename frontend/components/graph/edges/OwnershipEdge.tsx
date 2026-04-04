import React from 'react';
import { EdgeProps, getBezierPath } from '@xyflow/react';

/**
 * OwnershipEdge - Represents ownership relationships between nodes
 * Dashed 1.5px #3b82f6 line with no arrow markers
 * 
 * **Validates: Requirements 2.13**
 */
export function OwnershipEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
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
          stroke: '#3b82f6',
          strokeWidth: 1.5,
          strokeDasharray: '6 3',
        }}
        className="react-flow__edge-path"
        d={edgePath}
      />
    </>
  );
}
