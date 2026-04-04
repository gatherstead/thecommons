import { useState, useMemo, useEffect } from 'react';
import { getEvents, getTowns } from '../services/eventService';
import { type FrontendEvent, type TownOption } from '../models/eventsModels';
import { type TagId } from '../constants/tags';
import { useToggleSet } from './useToggleSet';

export type TownId = string;

export function useEvents() {
    const [events, setEvents] = useState<FrontendEvent[]>([]);
    const [towns, setTowns] = useState<TownOption[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    const { selected: selectedTags, toggle: toggleTag, clear: clearTags } = useToggleSet<TagId>([]);
    const { selected: selectedTowns, toggle: toggleTown, clear: clearTowns } = useToggleSet<TownId>([]);

    const fetchData = async () => {
        setIsLoading(true);
        const [data, townData] = await Promise.all([getEvents(), getTowns()]);
        setEvents(data);
        setTowns(townData);
        setIsLoading(false);
    };

    useEffect(() => {
        fetchData();
    }, []);

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
        selectedTags,
        selectedTowns,
        toggleTag,
        toggleTown,
        clearFilters,
        refetch: fetchData,
    };
}
