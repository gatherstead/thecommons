'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useEvents, type ViewMode } from '../hooks/useEvents';
import { useAuth } from '../hooks/useAuth';
import { type FrontendEvent } from '../models/eventsModels';
import { Sidebar } from '../components/layout/Sidebar';
import { TopBar } from '../components/layout/TopBar';
import { EventFeed } from '../components/events/EventFeed';
import { FeedStatusBar } from '../components/events/FeedStatusBar';
import { CalendarView } from '../components/events/CalendarView';
import { EventDetailModal } from '../components/events/EventDetailModal';

function isSameDay(a: Date, b: Date) {
  return (
    a.getDate() === b.getDate() &&
    a.getMonth() === b.getMonth() &&
    a.getFullYear() === b.getFullYear()
  );
}

export default function HomePage() {
  const [viewMode, setViewMode] = useState<ViewMode>('feed');
  const router = useRouter();
  const { user, logout } = useAuth();

  const {
    filteredEvents,
    towns,
    categories,
    isLoading,
    currentWindow,
    isLoadingWindow,
    setWindow,
    nextPage,
    prevPage,
    isLoadingPage,
    currentPage,
    totalPages,
    totalCount,
    fetchMonth,
    prefetchMonth,
    isLoadingMonth,
    selectedTags,
    selectedTowns,
    selectedCategory,
    toggleTag,
    toggleTown,
    setCategory,
    clearFilters,
  } = useEvents(viewMode);

  const [selectedEvent, setSelectedEvent] = useState<FrontendEvent | null>(null);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [calendarDisplayDate, setCalendarDisplayDate] = useState(() => {
    const d = new Date();
    d.setDate(1);
    return d;
  });

  const toggleView = () => {
    setViewMode((v) => {
      if (v === 'calendar') setSelectedDate(null);
      return v === 'feed' ? 'calendar' : 'feed';
    });
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

  const selectedSectionName =
    categories.find((c) => c.slug === selectedCategory)?.display_name ?? null;

  const hasFilters =
    selectedTags.length > 0 ||
    selectedTowns.length > 0 ||
    selectedCategory !== null ||
    selectedDate !== null;

  const sidebarProps = {
    isLoading,
    hasFilters,
    onClearFilters: handleClearFilters,
    onPostEvent: () => router.push('/post'),
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
    onSignIn: () => router.push('/auth/login?redirect=/'),
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
              <FeedStatusBar
                countLabel={displayedEvents.length < totalCount
                  ? `${displayedEvents.length} of ${totalCount} events`
                  : `${displayedEvents.length} event${displayedEvents.length !== 1 ? 's' : ''}`}
                currentWindow={currentWindow}
                onWindowChange={setWindow}
                categories={categories}
                selectedCategory={selectedCategory}
                onCategorySelect={setCategory}
              />
              <EventFeed
                events={displayedEvents}
                isLoading={isLoading}
                onEventClick={setSelectedEvent}
                towns={towns}
                footer={
                  <FeedStatusBar
                    countLabel={displayedEvents.length < totalCount
                      ? `${displayedEvents.length} of ${totalCount} events`
                      : `${displayedEvents.length} event${displayedEvents.length !== 1 ? 's' : ''}`}
                    currentWindow={currentWindow}
                    onWindowChange={setWindow}
                    categories={categories}
                    selectedCategory={selectedCategory}
                    onCategorySelect={setCategory}
                  />
                }
                currentPage={currentPage}
                totalPages={totalPages}
                totalCount={totalCount}
                onNextPage={nextPage}
                onPrevPage={prevPage}
                isLoadingPage={isLoadingPage}
                sectionName={selectedSectionName}
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

      <EventDetailModal
        event={selectedEvent}
        onClose={() => setSelectedEvent(null)}
        towns={towns}
      />
    </>
  );
}
