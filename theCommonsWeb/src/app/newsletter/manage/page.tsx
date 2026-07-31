import { Suspense } from 'react';
import type { Metadata } from 'next';
import { ManageForm } from './ManageForm';

export const metadata: Metadata = {
    title: 'Manage Newsletter — The Commons',
    description: 'Change your digest frequency or unsubscribe — no account required.',
};

export default function NewsletterManagePage() {
    return (
        <Suspense fallback={null}>
            <ManageForm />
        </Suspense>
    );
}
