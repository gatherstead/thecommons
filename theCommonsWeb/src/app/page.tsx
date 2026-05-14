'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useEvents, type ViewMode } from '../hooks/useEvents';
import { useAuth } from '../hooks/useAuth';
import { type EventPayload, type FrontendEvent } from '../models/eventsModels';
import { createEvent } from '../services/eventService';
import { Sidebar } from '../components/layout/Sidebar';
import { TopBar } from '../components/layout/TopBar';
import { EventFeed } from '../components/events/EventFeed';
import { CalendarView } from '../components/events/CalendarView';
import { AddEventModal } from '../components/events/AddEventModal';
import { EventDetailModal } from '../components/events/EventDetailModal';
import { AuthModal } from '../components/auth/AuthModal';

function isSameDay(a: Date, b: Date) {
  return (
    a.getDate() === b.getDate() &&
    a.getMonth() === b.getMonth() &&
    a.getFullYear() === b.getFullYear()
  );
}

export default function HomePage() {
  const [viewMode, setViewMode] = useState<ViewMode>('feed');
  const { user, token, isAuthenticated, isInitializing, logout } = useAuth();

  const {
    filteredEvents,
    towns,
    isLoading,
    showingPastEvents,
    isLoadingPast,
    loadPastEvents,
    fetchMonth,
    prefetchMonth,
    isLoadingMonth,
    selectedTags,
    selectedTowns,
    toggleTag,
    toggleTown,
    clearFilters,
    refetch,
  } = useEvents(viewMode);

  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<FrontendEvent | null>(null);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [calendarDisplayDate, setCalendarDisplayDate] = useState(() => {
    const d = new Date();
    d.setDate(1);
    return d;
  });

  // Holds the event payload the user filled in before hitting the auth wall.
  // Using a ref so the auto-submit effect always reads the latest value without
  // needing it as a reactive dependency.
  const pendingPayloadRef = useRef<EventPayload | null>(null);

  // Fire the pending submission as soon as the user finishes authenticating.
  useEffect(() => {
    if (isInitializing || !isAuthenticated || !token) return;
    const payload = pendingPayloadRef.current;
    if (!payload) return;

    pendingPayloadRef.current = null;
    setIsAuthModalOpen(false);

    createEvent(payload, token)
      .then(() => { alert('Event submitted for review!'); refetch(); })
      .catch((err: Error) => { alert(`Submission failed: ${err.message}`); });
  // refetch and createEvent are stable references; no need to list them.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, isInitializing, token]);

  // Called by AddEventModal when the user tries to submit without being logged in.
  const handleNeedsAuth = useCallback((payload: EventPayload) => {
    pendingPayloadRef.current = payload;
    setIsAddModalOpen(false);
    setIsAuthModalOpen(true);
  }, []);

  const toggleView = () => {
    setViewMode((v) => {
      if (v === 'calendar') setSelectedDate(null);
      return v === 'feed' ? 'calendar' : 'feed';
    });
  };

  const handleModalClose = () => {
    setIsAddModalOpen(false);
    refetch();
  };

  const handleClearFilters = () => {
    clearFilters();
    setSelectedDate(null);
  };

  const handleNavigateMonth = (date: Date) => {
    setCalendarDisplayDate(date);
    fetchMonth(date.getFullYear(), date.getMonth() + 1);
  };

  const handleDayClick = (date: Date | null) => {
    setSelectedDate(date);
    if (date) {
      setViewMode('calendar');
      const monthStart = new Date(date.getFullYear(), date.getMonth(), 1);
      setCalendarDisplayDate(monthStart);
      fetchMonth(date.getFullYear(), date.getMonth() + 1);
    }
  };

  const displayedEvents = useMemo(() => {
    if (viewMode !== 'feed' || !selectedDate) return filteredEvents;
    return filteredEvents.filter((e) => isSameDay(e.date, selectedDate));
  }, [filteredEvents, selectedDate, viewMode]);

  const hasFilters =
    selectedTags.length > 0 ||
    selectedTowns.length > 0 ||
    selectedDate !== null;

  const sidebarProps = {
    isLoading,
    hasFilters,
    onClearFilters: handleClearFilters,
    onPostEvent: () => setIsAddModalOpen(true),
    viewMode: viewMode as 'feed' | 'calendar',
    onToggleView: toggleView,
    events: filteredEvents,
    selectedDate,
    onDayClick: handleDayClick,
    displayDate: calendarDisplayDate,
    onNavigateMonth: handleNavigateMonth,
    isLoadingMonth,
    selectedTags,
    onTagToggle: toggleTag,
    currentUser: user,
    onSignIn: () => setIsAuthModalOpen(true),
    onSignOut: logout,
  };

  return (
    <>
      <TopBar
        towns={towns}
        selectedTowns={selectedTowns}
        onTownToggle={toggleTown}
        onClearFilters={handleClearFilters}
      />

      <main id="main-content" className="max-w-[1200px] mx-auto px-4 py-4">
        {viewMode === 'feed' ? (
          <div className="grid grid-cols-1 lg:grid-cols-6 gap-0">
            <div className="lg:col-span-4 lg:pr-10">
              <EventFeed
                events={displayedEvents}
                isLoading={isLoading}
                onEventClick={setSelectedEvent}
                towns={towns}
                showingPastEvents={showingPastEvents}
                isLoadingPast={isLoadingPast}
                onLoadPastEvents={loadPastEvents}
              />
            </div>
            <div className="lg:col-span-2 lg:pl-6 lg:border-l border-[var(--color-border-light)] mt-6 lg:mt-0">
              <Sidebar filteredCount={displayedEvents.length} {...sidebarProps} />
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-6 gap-0">
            <div className="lg:col-span-4 lg:pr-10">
              <CalendarView
                events={filteredEvents}
                onEventClick={setSelectedEvent}
                towns={towns}
                displayDate={calendarDisplayDate}
                onNavigateMonth={handleNavigateMonth}
                onPrefetchMonth={prefetchMonth}
                isLoadingMonth={isLoadingMonth}
              />
            </div>
            <div className="lg:col-span-2 lg:pl-6 lg:border-l border-[var(--color-border-light)] mt-6 lg:mt-0">
              <Sidebar filteredCount={filteredEvents.length} {...sidebarProps} />
            </div>
          </div>
        )}
      </main>

      <AddEventModal
        isOpen={isAddModalOpen}
        onClose={handleModalClose}
        towns={towns}
        onNeedsAuth={handleNeedsAuth}
      />

      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        onAuthenticated={() => setIsAuthModalOpen(false)}
        intro="Create an account to post your event to The Commons."
      />

      <EventDetailModal
        event={selectedEvent}
        onClose={() => setSelectedEvent(null)}
        towns={towns}
      />
    </>
  );
}
