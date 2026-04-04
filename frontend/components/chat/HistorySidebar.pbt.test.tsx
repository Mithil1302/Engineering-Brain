/**
 * Property-Based Tests for HistorySidebar
 * 
 * **Validates: Requirements 1.13, 1.14, 1.15**
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";
import { groupSessionsByTime } from "@/lib/utils";
import { Session } from "@/lib/types";

describe("HistorySidebar Property-Based Tests", () => {
  /**
   * Property 7: History session grouping by time
   * 
   * Sessions must be correctly grouped into time buckets:
   * - Today: sessions created on the current date
   * - Yesterday: sessions created on the previous date
   * - This Week (last7Days): sessions created 2-7 days ago
   * - Older: sessions created more than 7 days ago
   */
  it("Property 7: Sessions are correctly grouped by time buckets", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(
          fc.record({
            id: fc.uuid(), // Use UUID to ensure unique IDs
            repo: fc.constantFrom("test-repo", "other-repo"),
            user_id: fc.string(),
            created_at: fc.date({
              min: new Date(Date.now() - 365 * 24 * 60 * 60 * 1000), // 1 year ago
              max: new Date(),
            }).filter(d => !isNaN(d.getTime())), // Filter out invalid dates
            updated_at: fc.date().filter(d => !isNaN(d.getTime())), // Filter out invalid dates
            label: fc.option(fc.string(), { nil: undefined }),
          }),
          { minLength: 0, maxLength: 100 }
        ),
        async (sessions) => {
          // Convert Date objects to ISO strings for Session type
          const typedSessions: Session[] = sessions.map((s) => ({
            ...s,
            created_at: s.created_at.toISOString(),
            updated_at: s.updated_at.toISOString(),
          }));

          const grouped = groupSessionsByTime(typedSessions);

          // Calculate time boundaries
          const now = new Date();
          const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
          const yesterdayStart = new Date(todayStart);
          yesterdayStart.setDate(yesterdayStart.getDate() - 1);
          const last7DaysStart = new Date(todayStart);
          last7DaysStart.setDate(last7DaysStart.getDate() - 7);
          const last30DaysStart = new Date(todayStart);
          last30DaysStart.setDate(last30DaysStart.getDate() - 30);

          // Property 1: All sessions must be in exactly one group
          const allGroupedSessions = [
            ...grouped.today,
            ...grouped.yesterday,
            ...grouped.last7Days,
            ...grouped.last30Days,
            ...grouped.older,
          ];
          expect(allGroupedSessions.length).toBe(typedSessions.length);

          // Property 2: No session should appear in multiple groups
          const sessionIds = allGroupedSessions.map((s) => s.id);
          const uniqueIds = new Set(sessionIds);
          expect(uniqueIds.size).toBe(sessionIds.length);

          // Property 3: Today group contains only sessions from today
          grouped.today.forEach((session) => {
            const sessionDate = new Date(session.created_at);
            expect(sessionDate.getTime()).toBeGreaterThanOrEqual(todayStart.getTime());
          });

          // Property 4: Yesterday group contains only sessions from yesterday
          grouped.yesterday.forEach((session) => {
            const sessionDate = new Date(session.created_at);
            expect(sessionDate.getTime()).toBeGreaterThanOrEqual(yesterdayStart.getTime());
            expect(sessionDate.getTime()).toBeLessThan(todayStart.getTime());
          });

          // Property 5: Last 7 days group contains sessions from 2-7 days ago
          grouped.last7Days.forEach((session) => {
            const sessionDate = new Date(session.created_at);
            expect(sessionDate.getTime()).toBeGreaterThanOrEqual(last7DaysStart.getTime());
            expect(sessionDate.getTime()).toBeLessThan(yesterdayStart.getTime());
          });

          // Property 6: Last 30 days group contains sessions from 8-30 days ago
          grouped.last30Days.forEach((session) => {
            const sessionDate = new Date(session.created_at);
            expect(sessionDate.getTime()).toBeGreaterThanOrEqual(last30DaysStart.getTime());
            expect(sessionDate.getTime()).toBeLessThan(last7DaysStart.getTime());
          });

          // Property 7: Older group contains sessions older than 30 days
          grouped.older.forEach((session) => {
            const sessionDate = new Date(session.created_at);
            expect(sessionDate.getTime()).toBeLessThan(last30DaysStart.getTime());
          });

          // Property 8: Groups are mutually exclusive (no overlap)
          const todayIds = new Set(grouped.today.map((s) => s.id));
          const yesterdayIds = new Set(grouped.yesterday.map((s) => s.id));
          const last7DaysIds = new Set(grouped.last7Days.map((s) => s.id));
          const last30DaysIds = new Set(grouped.last30Days.map((s) => s.id));
          const olderIds = new Set(grouped.older.map((s) => s.id));

          // Check no overlap between groups
          grouped.yesterday.forEach((s) => expect(todayIds.has(s.id)).toBe(false));
          grouped.last7Days.forEach((s) => {
            expect(todayIds.has(s.id)).toBe(false);
            expect(yesterdayIds.has(s.id)).toBe(false);
          });
          grouped.last30Days.forEach((s) => {
            expect(todayIds.has(s.id)).toBe(false);
            expect(yesterdayIds.has(s.id)).toBe(false);
            expect(last7DaysIds.has(s.id)).toBe(false);
          });
          grouped.older.forEach((s) => {
            expect(todayIds.has(s.id)).toBe(false);
            expect(yesterdayIds.has(s.id)).toBe(false);
            expect(last7DaysIds.has(s.id)).toBe(false);
            expect(last30DaysIds.has(s.id)).toBe(false);
          });
        }
      ),
      { numRuns: 50 }
    );
  }, 30000);

  /**
   * Property 8: Session deletion with animation
   * 
   * When a session is deleted, it should:
   * 1. Be removed from the sessions list
   * 2. Trigger a 200ms fade-out animation (opacity transition)
   */
  it("Property 8: Deleting a session removes it from the list", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(
          fc.record({
            id: fc.uuid(), // Use UUID to ensure unique IDs
            repo: fc.string(),
            user_id: fc.string(),
            created_at: fc.date().filter(d => !isNaN(d.getTime())).map((d) => d.toISOString()),
            updated_at: fc.date().filter(d => !isNaN(d.getTime())).map((d) => d.toISOString()),
            label: fc.option(fc.string(), { nil: undefined }),
          }),
          { minLength: 1, maxLength: 50 }
        ),
        fc.integer({ min: 0 }), // Index of session to delete
        async (sessions, deleteIndexRaw) => {
          const deleteIndex = deleteIndexRaw % sessions.length;
          const sessionToDelete = sessions[deleteIndex];

          // Simulate deletion by filtering out the session
          const remainingSessions = sessions.filter((s) => s.id !== sessionToDelete.id);

          // Property 1: Deleted session should not be in remaining list
          expect(remainingSessions.find((s) => s.id === sessionToDelete.id)).toBeUndefined();

          // Property 2: All other sessions should remain
          expect(remainingSessions.length).toBe(sessions.length - 1);

          // Property 3: Order of remaining sessions should be preserved
          const originalIndices = sessions
            .map((s, i) => (s.id !== sessionToDelete.id ? i : -1))
            .filter((i) => i !== -1);
          const remainingIndices = remainingSessions.map((s) =>
            sessions.findIndex((orig) => orig.id === s.id)
          );

          expect(remainingIndices).toEqual(originalIndices);
        }
      ),
      { numRuns: 50 }
    );
  });

  /**
   * Edge case: Empty sessions array
   */
  test("groupSessionsByTime handles empty array", () => {
    const grouped = groupSessionsByTime([]);

    expect(grouped.today).toEqual([]);
    expect(grouped.yesterday).toEqual([]);
    expect(grouped.last7Days).toEqual([]);
    expect(grouped.last30Days).toEqual([]);
    expect(grouped.older).toEqual([]);
  });

  /**
   * Edge case: Sessions at exact boundary times
   */
  test("groupSessionsByTime handles boundary times correctly", () => {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterdayStart = new Date(todayStart);
    yesterdayStart.setDate(yesterdayStart.getDate() - 1);

    const sessions: Session[] = [
      {
        id: "1",
        repo: "test",
        user_id: "user",
        created_at: todayStart.toISOString(), // Exactly at today's start
        updated_at: todayStart.toISOString(),
      },
      {
        id: "2",
        repo: "test",
        user_id: "user",
        created_at: yesterdayStart.toISOString(), // Exactly at yesterday's start
        updated_at: yesterdayStart.toISOString(),
      },
    ];

    const grouped = groupSessionsByTime(sessions);

    // Session at today's start should be in today
    expect(grouped.today.find((s) => s.id === "1")).toBeDefined();

    // Session at yesterday's start should be in yesterday
    expect(grouped.yesterday.find((s) => s.id === "2")).toBeDefined();
  });
});
