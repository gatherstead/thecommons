import { useState, useMemo } from 'react';
import { useEvents } from './hooks/useEvents';
import { type FrontendEvent } from './models/eventsModels';
import { Header } from './components/layout/Header';
import { Footer } from './components/layout/Footer';
import { Sidebar } from './components/layout/Sidebar';
import { TopBar } from './components/layout/TopBar';
import { EventFeed } from './components/events/EventFeed';
import { CalendarView } from './components/events/CalendarView';
import { AddEventModal } from './components/events/AddEventModal';
import { EventDetailModal } from './components/events/EventDetailModal';

type ViewMode = 'feed' | 'calendar';

function isSameDay(a: Date, b: Date) {
  return (
    a.getDate() === b.getDate() &&
    a.getMonth() === b.getMonth() &&
    a.getFullYear() === b.getFullYear()
  );
}

function App() {
  const {
    filteredEvents,
    towns,
    isLoading,
    selectedTags,
    selectedTowns,
    toggleTag,
    toggleTown,
    clearFilters,
    refetch,
  } = useEvents();

  const [viewMode, setViewMode] = useState<ViewMode>('feed');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<FrontendEvent | null>(null);

  // Date selected via mini calendar — drives both feed filter and calendar jump
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);

  const toggleView = () => {
    setViewMode(v => {
      // Clear the selected date when returning to feed so nothing stays filtered
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

  // Clicking a day in the mini calendar: switch to calendar view and open that day
  const handleDayClick = (date: Date | null) => {
    setSelectedDate(date);
    if (date) setViewMode('calendar');
  };

  // Feed-mode date filter (only used when staying in feed view)
  const displayedEvents = useMemo(() => {
    if (viewMode !== 'feed' || !selectedDate) return filteredEvents;
    return filteredEvents.filter(e => isSameDay(e.date, selectedDate));
  }, [filteredEvents, selectedDate, viewMode]);

  const hasFilters = selectedTags.length > 0 || selectedTowns.length > 0 || selectedDate !== null;

  const sidebarProps = {
    isLoading,
    hasFilters,
    onClearFilters: handleClearFilters,
    onPostEvent: () => setIsAddModalOpen(true),
    viewMode,
    onToggleView: toggleView,
    events: filteredEvents,
    selectedDate,
    onDayClick: handleDayClick,
    selectedTags,
    onTagToggle: toggleTag,
  };

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-1 focus:bg-[var(--color-accent)] focus:text-white focus:text-sm"
      >
        Skip to content
      </a>

      <Header />

      {/* Towns bar — horizontal strip below masthead */}
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
                jumpToDay={selectedDate}
              />
            </div>
            <div className="lg:col-span-2 lg:pl-6 lg:border-l border-[var(--color-border-light)] mt-6 lg:mt-0">
              <Sidebar filteredCount={filteredEvents.length} {...sidebarProps} />
            </div>
          </div>
        )}
      </main>

      <Footer />

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
    </div>
  );
}

export default App;
