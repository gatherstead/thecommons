import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

describe('db tier smoke', () => {
    it('renders into jsdom with jest-dom matchers available', () => {
        render(<div>hello</div>);
        expect(screen.getByText('hello')).toBeInTheDocument();
    });
});
