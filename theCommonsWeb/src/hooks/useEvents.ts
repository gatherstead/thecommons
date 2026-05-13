'use client';

import { useState, useMemo, useEffect } from 'react';
import { getEvents, getTowns } from '../services/eventService';
import { type FrontendEvent, type TownOption } from '../models/eventsModels';
import { type TagId } from '../constants/tags';
import { useToggleSet } from './useToggleSet';

export type TownId = string;
export type ViewMode = 'feed' | 'calendar';

export function useEvents(viewMode: ViewMode = 'feed') {
    const [events, setEvents] = useState<FrontendEvent[]>([]);
    const [towns, setTowns] = useState<TownOption[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [showingPastEvents, setShowingPastEvents] = useState(false);
    const [isLoadingPast, setIsLoadingPast] = useState(false);

    const { selected: selectedTags, toggle: toggleTag, clear: clearTags } = useToggleSet<TagId>([]);
    const { selected: selectedTowns, toggle: toggleTown, clear: clearTowns } = useToggleSet<TownId>([]);

    const fetchEvents = async (includePast: boolean) => {
        setIsLoading(true);
        let params: Parameters<typeof getEvents>[0];
        if (includePast) {
            params = { include_past: true };
        } else {
            const before = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
            params = { before: before.toISOString() };
        }
        const [data, townData] = await Promise.all([getEvents(params), getTowns()]);
        setEvents(data);
        setTowns(townData);
        setIsLoading(false);
    };

    useEffect(() => {
        setShowingPastEvents(false);
        fetchEvents(viewMode === 'calendar');
    }, [viewMode]);

    const loadPastEvents = async () => {
        setIsLoadingPast(true);
        const data = await getEvents({ include_past: true });
        setEvents(data);
        setShowingPastEvents(true);
        setIsLoadingPast(false);
    };

    const filteredEvents = useMemo(() => {
        return events
            .filter(event => {
                if (selectedTowns.length > 0 && !selectedTowns.includes(event.town as TownId)) {
                    return false;
                }
                if (selectedTags.length > 0 && !selectedTags.every(tag => event.tags.includes(tag))) {
                    return false;
                }
                return true;
            })
            .sort((a, b) => a.date.getTime() - b.date.getTime());
    }, [selectedTags, selectedTowns, events]);

    const clearFilters = () => {
        clearTags();
        clearTowns();
    };

    return {
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
        refetch: () => fetchEvents(viewMode === 'calendar' || showingPastEvents),
    };
}
