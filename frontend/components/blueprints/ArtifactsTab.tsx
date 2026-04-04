"use client";

import { useState, useEffect } from "react";
import { useBlueprintArtifact } from "@/hooks/useBlueprintData";
import { useSession } from "@/store/session";
import { blueprintsApi } from "@/lib/api";
import { ChevronRight, ChevronDown, FileCode, Folder, Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import dynamic from "next/dynamic";

// Dynamically import Monaco Editor to avoid SSR issues
const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="h-[600px] bg-slate-800 rounded animate-pulse flex items-center justify-center">
      <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
    </div>
  ),
});

interface ArtifactsTabProps {
  blueprintId: string;
}

interface FileNode {
  name: string;
  path: string;
  type: "file" | "folder";
  children?: FileNode[];
}

function buildFileTree(artifacts: any[]): FileNode[] {
  const root: FileNode[] = [];
  const folderMap: Record<string, FileNode> = {};

  artifacts.forEach((artifact) => {
    const parts = artifact.file_path.split("/");
    let currentLevel = root;
    let currentPath = "";

    parts.forEach((part: string, index: number) => {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isFile = index === parts.length - 1;

      if (isFile) {
        currentLevel.push({
          name: part,
          path: artifact.file_path,
          type: "file",
        });
      } else {
        let folder = folderMap[currentPath];
        if (!folder) {
          folder = {
            name: part,
            path: currentPath,
            type: "folder",
            children: [],
          };
          folderMap[currentPath] = folder;
          currentLevel.push(folder);
        }
        currentLevel = folder.children!;
      }
    });
  });

  return root;
}

function FileTreeNode({
  node,
  selectedPath,
  onSelect,
  level = 0,
}: {
  node: FileNode;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  level?: number;
}) {
  const [isExpanded, setIsExpanded] = useState(true);

  if (node.type === "file") {
    return (
      <button
        onClick={() => onSelect(node.path)}
        className={`w-full text-left px-3 py-1.5 flex items-center gap-2 transition-colors ${
          selectedPath === node.path
            ? "bg-indigo-600/20 text-indigo-300"
            : "text-slate-400 hover:text-white hover:bg-slate-800/50"
        }`}
        style={{ paddingLeft: `${level * 12 + 12}px` }}
      >
        <FileCode className="w-3 h-3 shrink-0" />
        <span className="text-[11px] truncate">{node.name}</span>
      </button>
    );
  }

  return (
    <div>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full text-left px-3 py-1.5 flex items-center gap-2 text-slate-400 hover:text-white hover:bg-slate-800/50 transition-colors"
        style={{ paddingLeft: `${level * 12 + 12}px` }}
      >
        {isExpanded ? (
          <ChevronDown className="w-3 h-3 shrink-0" />
        ) : (
          <ChevronRight className="w-3 h-3 shrink-0" />
        )}
        <Folder className="w-3 h-3 shrink-0" />
        <span className="text-[11px] truncate">{node.name}</span>
      </button>
      {isExpanded && node.children && (
        <div>
          {node.children.map((child, i) => (
            <FileTreeNode
              key={i}
              node={child}
              selectedPath={selectedPath}
              onSelect={onSelect}
              level={level + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function getLanguageFromPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "yaml":
    case "yml":
      return "yaml";
    case "json":
      return "json";
    case "ts":
    case "tsx":
      return "typescript";
    case "js":
    case "jsx":
      return "javascript";
    case "py":
      return "python";
    case "go":
      return "go";
    case "proto":
      return "proto";
    case "dockerfile":
      return "dockerfile";
    default:
      if (path.includes("Dockerfile")) return "dockerfile";
      return "plaintext";
  }
}

export function ArtifactsTab({ blueprintId }: ArtifactsTabProps) {
  const { authHeaders } = useSession();
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [isDownloading, setIsDownloading] = useState(false);

  const { data: artifactContent, isLoading: isLoadingContent } = useBlueprintArtifact(
    blueprintId,
    selectedPath
  );

  // Build file tree from blueprint artifacts
  useEffect(() => {
    // In a real implementation, we'd fetch the artifact list from the blueprint
    // For now, we'll use a placeholder
    const mockArtifacts = [
      { file_path: "services/api-gateway/Dockerfile" },
      { file_path: "services/api-gateway/k8s/deployment.yaml" },
      { file_path: "services/api-gateway/k8s/service.yaml" },
      { file_path: "services/auth-service/Dockerfile" },
      { file_path: "services/auth-service/k8s/deployment.yaml" },
      { file_path: "api/api-gateway/openapi.yaml" },
      { file_path: "proto/auth.proto" },
    ];
    setFileTree(buildFileTree(mockArtifacts));
  }, [blueprintId]);

  const handleDownloadAll = async () => {
    setIsDownloading(true);
    try {
      const { url, headers } = blueprintsApi.downloadArtifacts(blueprintId, authHeaders());
      const response = await fetch(url, { headers });
      const blob = await response.blob();
      const downloadUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = `blueprint-${blueprintId}-artifacts.zip`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(downloadUrl);
    } catch (error) {
      console.error("Failed to download artifacts:", error);
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="flex gap-3 h-[600px]">
      {/* File tree - 200px */}
      <div className="w-[200px] shrink-0 rounded-xl border border-slate-700/40 overflow-hidden bg-slate-800/20">
        <div className="p-2 border-b border-slate-700/40 flex items-center justify-between">
          <span className="text-[10px] text-slate-500 uppercase tracking-wider">Files</span>
        </div>
        <div className="overflow-y-auto h-[calc(100%-40px)]">
          {fileTree.map((node, i) => (
            <FileTreeNode
              key={i}
              node={node}
              selectedPath={selectedPath}
              onSelect={setSelectedPath}
            />
          ))}
        </div>
      </div>

      {/* Monaco Editor - flex-1 */}
      <div className="flex-1 rounded-xl border border-slate-700/40 overflow-hidden bg-slate-900 relative">
        {/* Download button */}
        <div className="absolute top-2 right-2 z-10">
          <Button
            size="sm"
            variant="outline"
            onClick={handleDownloadAll}
            disabled={isDownloading}
            className="bg-slate-800/80 border-slate-700"
          >
            {isDownloading ? (
              <>
                <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                Downloading...
              </>
            ) : (
              <>
                <Download className="w-3 h-3 mr-1" />
                Download all
              </>
            )}
          </Button>
        </div>

        {selectedPath ? (
          isLoadingContent ? (
            <div className="h-full flex items-center justify-center">
              <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
            </div>
          ) : (
            <MonacoEditor
              height="100%"
              language={getLanguageFromPath(selectedPath)}
              theme="vs-dark"
              value={artifactContent as string || "// No content available"}
              options={{
                readOnly: true,
                minimap: { enabled: true },
                lineNumbers: "on",
                wordWrap: "on",
                scrollBeyondLastLine: false,
                fontSize: 13,
              }}
            />
          )
        ) : (
          <div className="h-full flex items-center justify-center">
            <p className="text-xs text-slate-500">Select a file to preview</p>
          </div>
        )}
      </div>
    </div>
  );
}
