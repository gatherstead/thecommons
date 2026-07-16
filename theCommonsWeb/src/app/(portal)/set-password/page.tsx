import { Suspense } from 'react';
import { SetPasswordForm } from './SetPasswordForm';

export default function SetPasswordPage() {
    return (
        <Suspense fallback={null}>
            <SetPasswordForm />
        </Suspense>
    );
}
