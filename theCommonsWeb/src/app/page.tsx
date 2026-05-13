'use client';

import { useState, useMemo } from 'react';
import { useEvents, type ViewMode } from '../hooks/useEvents';
import { useAuth } from '../hooks/useAuth';
import { type FrontendEvent } from '../models/eventsModels';
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
  const { user, logout } = useAuth();

  const {
    filteredEvents,
    towns,
    isLoading,
    showingPastEvents,
    isLoadingPast,
    loadPastEvents,
    selectedTags,
    selectedTowns,
    toggleTag,
    toggleTown,
    clearFilters,
    refetch,
  } = useEvents(viewMode);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<FrontendEvent | null>(
    null,
  );

  const [selectedDate, setSelectedDate] = useState<Date | null>(null);

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

  const handleDayClick = (date: Date | null) => {
    setSelectedDate(date);
    if (date) setViewMode('calendar');
  };

  const handlePostEvent = () => {
    if (user) {
      setIsAddModalOpen(true);
    } else {
      setIsAuthModalOpen(true);
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
    onPostEvent: handlePostEvent,
    viewMode: viewMode as 'feed' | 'calendar',
    onToggleView: toggleView,
    events: filteredEvents,
    selectedDate,
    onDayClick: handleDayClick,
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
              <Sidebar
                filteredCount={displayedEvents.length}
                {...sidebarProps}
              />
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-6 gap-0">
            <div className="lg:col-span-4 lg:pr-10">
              <CalendarView
                events={filteredEvents}
                onEventClick={setSelectedEvent}
                towns={towns}
                jumpToDay={selectedDate}
              />
            </div>
            <div className="lg:col-span-2 lg:pl-6 lg:border-l border-[var(--color-border-light)] mt-6 lg:mt-0">
              <Sidebar
                filteredCount={filteredEvents.length}
                {...sidebarProps}
              />
            </div>
          </div>
        )}
      </main>

      <AddEventModal
        isOpen={isAddModalOpen}
        onClose={handleModalClose}
        towns={towns}
      />

      <EventDetailModal
        event={selectedEvent}
        onClose={() => setSelectedEvent(null)}
        towns={towns}
      />

      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        onAuthenticated={() => {
          setIsAuthModalOpen(false);
          setIsAddModalOpen(true);
        }}
        intro="Create an account to post events to The Commons."
      />
    </>
  );
}
