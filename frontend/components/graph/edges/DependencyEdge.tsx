import React from 'react';
import { EdgeProps, getBezierPath } from '@xyflow/react';

/**
 * DependencyEdge - Represents dependency relationships between nodes
 * Solid 1.5px #6b7280 line with arrow marker at target end
 * 
 * **Validates: Requirements 2.12**
 */
export function DependencyEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
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
          stroke: '#6b7280',
          strokeWidth: 1.5,
        }}
        className="react-flow__edge-path"
        d={edgePath}
        markerEnd={markerEnd}
      />
    </>
  );
}
