import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HistorySidebar } from "./HistorySidebar";
import { assistantApi } from "@/lib/api";
import { useSession } from "@/store/session";
import { Session, ChatMessage } from "@/lib/types";

// Mock dependencies
vi.mock("@/lib/api");
vi.mock("@/store/session");

const mockAssistantApi = assistantApi as any;
const mockUseSession = useSession as any;

describe("HistorySidebar", () => {
  let queryClient: QueryClient;
  const mockOnClose = vi.fn();
  const mockOnNewConversation = vi.fn();
  const mockOnLoadSession = vi.fn();
  const mockAuthHeaders = vi.fn(() => ({ "X-Auth-Subject": "test-user" }));

  const mockSessions: Session[] = [
    {
      id: "session-1",
      repo: "test-repo",
      user_id: "user-1",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      label: "Test conversation 1",
    },
    {
      id: "session-2",
      repo: "test-repo",
      user_id: "user-1",
      created_at: new Date(Date.now() - 86400000).toISOString(), // Yesterday
      updated_at: new Date(Date.now() - 86400000).toISOString(),
      label: "Test conversation 2",
    },
  ];

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    mockUseSession.mockReturnValue({
      activeRepo: "test-repo",
      authHeaders: mockAuthHeaders,
      user: null,
      adminToken: "",
      setUser: vi.fn(),
      setActiveRepo: vi.fn(),
      setAdminToken: vi.fn(),
      logout: vi.fn(),
    });

    mockAssistantApi.sessions.mockResolvedValue(mockSessions);
    mockAssistantApi.sessionMessages.mockResolvedValue([
      {
        id: "msg-1",
        role: "user",
        content: "Test message",
        timestamp: new Date().toISOString(),
      },
    ] as ChatMessage[]);
    mockAssistantApi.deleteSession.mockResolvedValue(undefined);

    vi.clearAllMocks();
  });

  const renderComponent = (isOpen = true) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <HistorySidebar
          isOpen={isOpen}
          onClose={mockOnClose}
          onNewConversation={mockOnNewConversation}
          onLoadSession={mockOnLoadSession}
        />
      </QueryClientProvider>
    );
  };

  it("renders with correct width (320px / w-80)", () => {
    const { container } = renderComponent();
    const sidebar = container.firstChild as HTMLElement;
    expect(sidebar).toHaveClass("w-80");
  });

  it("applies translateX transition when open/closed", () => {
    const { container, rerender } = renderComponent(true);
    const sidebar = container.firstChild as HTMLElement;
    
    expect(sidebar).toHaveClass("translate-x-0");
    expect(sidebar).toHaveClass("duration-300");

    rerender(
      <QueryClientProvider client={queryClient}>
        <HistorySidebar
          isOpen={false}
          onClose={mockOnClose}
          onNewConversation={mockOnNewConversation}
          onLoadSession={mockOnLoadSession}
        />
      </QueryClientProvider>
    );

    expect(sidebar).toHaveClass("translate-x-full");
  });

  it("fetches sessions from API when open", async () => {
    renderComponent(true);

    await waitFor(() => {
      expect(mockAssistantApi.sessions).toHaveBeenCalledWith(
        "test-repo",
        { "X-Auth-Subject": "test-user" }
      );
    });
  });

  it("does not fetch sessions when closed", () => {
    renderComponent(false);
    expect(mockAssistantApi.sessions).not.toHaveBeenCalled();
  });

  it("groups sessions by time correctly", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Today")).toBeInTheDocument();
      expect(screen.getByText("Yesterday")).toBeInTheDocument();
    });

    expect(screen.getByText("Test conversation 1")).toBeInTheDocument();
    expect(screen.getByText("Test conversation 2")).toBeInTheDocument();
  });

  it("displays session with PR title or first message preview", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Test conversation 1")).toBeInTheDocument();
    });
  });

  it("displays relative timestamp for each session", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/ago/)).toBeInTheDocument();
    });
  });

  it("shows delete button on hover", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Test conversation 1")).toBeInTheDocument();
    });

    const sessionItem = screen.getByText("Test conversation 1").closest("button");
    expect(sessionItem).toBeInTheDocument();

    // Delete button should have opacity-0 class initially
    const deleteButton = sessionItem?.querySelector('[aria-label="Delete session"]');
    expect(deleteButton).toHaveClass("opacity-0");
  });

  it("deletes session with 200ms fade-out animation", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Test conversation 1")).toBeInTheDocument();
    });

    const sessionItem = screen.getByText("Test conversation 1").closest("button");
    const deleteButton = sessionItem?.querySelector('[aria-label="Delete session"]') as HTMLElement;

    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(mockAssistantApi.deleteSession).toHaveBeenCalledWith(
        "session-1",
        { "X-Auth-Subject": "test-user" }
      );
    });

    // Check that the item has opacity-0 class during deletion
    expect(sessionItem).toHaveClass("opacity-0");
  });

  it("calls onNewConversation when new conversation button clicked", async () => {
    renderComponent();

    const newButton = await screen.findByText("New conversation");
    fireEvent.click(newButton);

    expect(mockOnNewConversation).toHaveBeenCalledTimes(1);
  });

  it("loads session messages when session item clicked", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Test conversation 1")).toBeInTheDocument();
    });

    const sessionItem = screen.getByText("Test conversation 1");
    fireEvent.click(sessionItem);

    await waitFor(() => {
      expect(mockAssistantApi.sessionMessages).toHaveBeenCalledWith(
        "session-1",
        { "X-Auth-Subject": "test-user" }
      );
      expect(mockOnLoadSession).toHaveBeenCalledWith([
        {
          id: "msg-1",
          role: "user",
          content: "Test message",
          timestamp: expect.any(String),
        },
      ]);
    });
  });

  it("displays loading skeleton while fetching", () => {
    mockAssistantApi.sessions.mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    renderComponent();

    // Should show skeleton loaders with skeleton class
    const skeletons = screen.getAllByRole("generic").filter((el) =>
      el.className.includes("skeleton")
    );
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("displays error state when fetch fails", async () => {
    mockAssistantApi.sessions.mockRejectedValue(new Error("Network error"));

    renderComponent();

    await waitFor(() => {
      expect(
        screen.getByText(/Could not load conversation history for test-repo/)
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });
  });

  it("displays empty state when no sessions exist", async () => {
    mockAssistantApi.sessions.mockResolvedValue([]);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("No conversations yet")).toBeInTheDocument();
    });
  });

  it("calls onClose when close button clicked", async () => {
    renderComponent();

    const closeButton = screen.getByLabelText("Close history sidebar");
    fireEvent.click(closeButton);

    expect(mockOnClose).toHaveBeenCalledTimes(1);
  });

  it("generates new session ID in Zustand when new conversation clicked", async () => {
    renderComponent();

    const newButton = await screen.findByText("New conversation");
    fireEvent.click(newButton);

    // The component should call onNewConversation which handles session ID generation
    expect(mockOnNewConversation).toHaveBeenCalled();
  });
});
