import { useState, useMemo, useEffect } from 'react';
import { TagFilter, type TagId } from './components/TagFilter';
import { TownMultiselect, type TownId } from './components/TownMultiselect';
import { EventCard } from './components/EventCard';
import { AddEventModal } from './components/AddEventModal';
import { EventModal } from './components/EventModal';
import { CalendarView } from './components/CalendarView';


import { getEvents } from './services/eventService';
import { type FrontendEvent } from './models/eventsModels';

type ViewMode = 'feed' | 'calendar';

function App() {
  const [events, setEvents] = useState<FrontendEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [selectedTags, setSelectedTags] = useState<TagId[]>([]);
  const [selectedTowns, setSelectedTowns] = useState<TownId[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('feed');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);

  // State for viewing a specific event's details
  const [selectedEvent, setSelectedEvent] = useState<FrontendEvent | null>(null);


  // Fetch events when the component loads
  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setIsLoading(true);
    const data = await getEvents();
    setEvents(data);
    setIsLoading(false);
  };

  // Called when a new event is successfully posted
  const handleModalClose = () => {
    setIsAddModalOpen(false);
    fetchData();
    // Refresh the feed immediately
    //TODO: Is this needed?
  };

  const handleTagToggle = (tagId: TagId) => {
    setSelectedTags(prev =>
      prev.includes(tagId)
        ? prev.filter(t => t !== tagId)
        : [...prev, tagId]
    );
  };

  const handleTownToggle = (townId: TownId) => {
    setSelectedTowns(prev =>
      prev.includes(townId)
        ? prev.filter(t => t !== townId)
        : [...prev, townId]
    );
  };

  // --- FILTERING LOGIC ---
  const filteredEvents = useMemo(() => {
    return events
      .filter(event => {
        // Town Filter
        if (selectedTowns.length > 0 && !selectedTowns.includes(event.town as TownId)) {
          return false;
        }
        // Tag Filter
        // Note: Backend tags are strings. We check if the event tags include our filter ID.
        if (selectedTags.length > 0 && !selectedTags.some(tag => event.tags.includes(tag))) {
          return false;
        }
        return true;
      })
      .sort((a, b) => a.date.getTime() - b.date.getTime());
  }, [selectedTags, selectedTowns, events]);

  const featuredEvent = filteredEvents[0];
  const regularEvents = filteredEvents.slice(1);

  const today = new Date();
  const formattedDate = today.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      {/* --- HEADER --- */}
      <header className="border-b-4 border-[var(--color-border)] relative">
        <div className="max-w-6xl mx-auto px-4 py-6">
          <div className="flex justify-between items-start mb-4">
            <div className="hidden md:block w-32 border-t border-[var(--color-border)] mt-4"></div>
            <div className="text-center flex-1">
              <p className="text-xs uppercase tracking-[0.3em] text-[var(--color-muted)] mb-2">
                Your Town's Digital Gathering Place
              </p>
              <h1 className="font-[var(--font-headline)] text-5xl md:text-7xl font-black tracking-tight mb-2">
                The Commons
              </h1>
            </div>
            <div className="hidden md:block w-32 border-t border-[var(--color-border)] mt-4 text-right">
              <button
                onClick={() => setViewMode(viewMode === 'feed' ? 'calendar' : 'feed')}
                className="text-xs uppercase font-bold border-b border-[var(--color-border)] hover:text-[var(--color-accent)] cursor-pointer pb-1"
              >
                {viewMode === 'feed' ? 'View Calendar' : 'View Feed'}
              </button>
            </div>
          </div>

          <div className="newspaper-double-border my-4">
            <p className="text-sm font-[var(--font-accent)] italic text-center">
              "Find your next excuse to stay local"
            </p>
          </div>
          <div className="flex justify-center items-center text-sm text-[var(--color-muted)]">
            <span>{formattedDate}</span>
          </div>
        </div>
      </header>

      {/* --- MAIN CONTENT --- */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">

          {/* --- SIDEBAR --- */}
          <aside className="lg:col-span-1 space-y-6">
            <button
              onClick={() => setIsAddModalOpen(true)}
              className="w-full py-4 bg-[var(--color-paper)] text-[var(--color-ink)] font-bold uppercase tracking-widest hover:bg-[var(--color-accent)] transition-colors cursor-pointer newspaper-border shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] active:shadow-none active:translate-x-[2px] active:translate-y-[2px]"
            >
              Post an Event +
            </button>

            <hr className="newspaper-divider-thin" />

            <div>
              <h3 className="font-[var(--font-headline)] text-sm uppercase tracking-widest mb-3 font-semibold">
                Select Your Town
              </h3>
              <TownMultiselect
                selectedTowns={selectedTowns}
                onTownToggle={handleTownToggle}
              />
            </div>

            <TagFilter
              selectedTags={selectedTags}
              onTagToggle={handleTagToggle}
            />

            {/* Instagram Plug Section */}
            <div className="newspaper-border p-4 bg-[#f9f7f2]">
              <h3 className="font-[var(--font-headline)] text-xs uppercase tracking-widest mb-2 font-bold border-b border-black pb-1">
                Follow the Feed
              </h3>
              <p className="text-xs mb-3 italic">Get daily event highlights on your phone.</p>
              <a
                href="https://instagram.com"
                target="_blank"
                rel="noreferrer"
                className="text-sm font-bold flex items-center gap-2 hover:text-[var(--color-accent)]"
              >
                <span>📸 @TheCommonsLocal</span>
              </a>
            </div>

            <div className="md:hidden">
              <button
                onClick={() => setViewMode(viewMode === 'feed' ? 'calendar' : 'feed')}
                className="w-full py-2 bg-[var(--color-ink)] text-[var(--color-paper)] font-bold uppercase"
              >
                {viewMode === 'feed' ? 'Switch to Calendar' : 'Switch to Feed'}
              </button>
            </div>

            {(selectedTags.length > 0 || selectedTowns.length > 0) && (
              <button
                onClick={() => {
                  setSelectedTags([]);
                  setSelectedTowns([]);
                }}
                className="w-full py-2 text-sm text-[var(--color-accent)] hover:underline cursor-pointer"
              >
                Clear all filters
              </button>
            )}
          </aside>

          {/* --- EVENT FEED / CALENDAR --- */}
          <section className="lg:col-span-3">
            {viewMode === 'feed' ? (
              <>
                <div className="border-b-2 border-[var(--color-border)] pb-2 mb-6">
                  <h2 className="font-[var(--font-headline)] text-2xl font-bold">
                    Upcoming Events
                  </h2>
                  <p className="text-sm text-[var(--color-muted)]">
                    {isLoading
                      ? 'Checking for local happenings...'
                      : `${filteredEvents.length} event${filteredEvents.length !== 1 ? 's' : ''} found`
                    }
                  </p>
                </div>

                {isLoading ? (
                  <div className="text-center py-20 opacity-50">
                    <p className="font-[var(--font-headline)] uppercase tracking-widest animate-pulse">Loading Events...</p>
                  </div>
                ) : filteredEvents.length === 0 ? (
                  <div className="text-center py-12 border-2 border-dashed border-[var(--color-border)]">
                    <p className="text-lg text-[var(--color-muted)] font-[var(--font-headline)]">
                      No events match your current filters.
                    </p>
                    <p className="text-sm text-[var(--color-muted)] mt-2">
                      Try adjusting your town or interest selections.
                    </p>
                  </div>
                ) : (
                  <>
                    {featuredEvent && (
                      <EventCard
                        event={featuredEvent}
                        featured
                        onClick={() => setSelectedEvent(featuredEvent)}
                      />
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
                      <div>
                        {regularEvents.filter((_, i) => i % 2 === 0).map(event => (
                          <EventCard
                            key={event.id}
                            event={event}
                            onClick={() => setSelectedEvent(event)}
                          />
                        ))}
                      </div>
                      <div>
                        {regularEvents.filter((_, i) => i % 2 === 1).map(event => (
                          <EventCard
                            key={event.id}
                            event={event}
                            onClick={() => setSelectedEvent(event)}
                          />
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </>
            ) : (
              // Calendar View
              <CalendarView events={filteredEvents} />
            )}
          </section>
        </div>
      </main>

      {/* --- FOOTER --- */}
      <footer className="border-t-4 border-[var(--color-border)] mt-12">
        <div className="max-w-6xl mx-auto px-4 py-8">
          <div className="text-center">
            <p className="font-[var(--font-headline)] text-xl font-bold mb-2">
              The Commons
            </p>
            <p className="text-sm text-[var(--color-muted)] mb-4">
              Connecting neighbors, supporting local businesses, building community.
            </p>
            <div className="flex justify-center items-center gap-4 mb-6">
              <div className="flex-1 max-w-xs border-t newspaper-divider-thin" />
              <div className="flex gap-4 px-4 text-xs font-bold uppercase tracking-widest">
                <a href="#" className="hover:text-[var(--color-accent)]">About</a>
                <a href="#" className="hover:text-[var(--color-accent)]">Contact</a>
                <a href="#" className="hover:text-[var(--color-accent)]">Privacy</a>
              </div>
              <div className="flex-1 max-w-xs border-t newspaper-divider-thin" />
            </div>
            <p className="text-xs text-[var(--color-muted)]">
              © {today.getFullYear()} The Commons. All rights reserved.
            </p>
          </div>
        </div>
      </footer>

      {/* --- MODALS --- */}
      <AddEventModal
        isOpen={isAddModalOpen}
        onClose={handleModalClose} // Now triggers a refresh when closed
      />

      <EventModal
        event={selectedEvent ? { ...selectedEvent, date: selectedEvent.date.toISOString() } as any : null}
        onClose={() => setSelectedEvent(null)}
      />
    </div>
  );
}

export default App;