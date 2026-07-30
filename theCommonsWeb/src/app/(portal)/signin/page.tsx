import { Suspense } from 'react';
import { SignInForm } from './SignInForm';

export default function SignInPage() {
    return (
        <Suspense fallback={null}>
            <SignInForm />
        </Suspense>
    );
}
