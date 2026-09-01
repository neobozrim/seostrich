'use client';

import React, { useEffect, useRef, useState } from 'react';
import { LogOut } from 'lucide-react';

interface ProfileMenuProps {
  username: string | null;
  authRequired: boolean;
  onLogout: () => void;
}

export function ProfileMenu({ username, authRequired, onLogout }: ProfileMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const initial = (username || 'G').charAt(0).toUpperCase();

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        // Not a brown bubble: the brand mark already owns that treatment, so
        // the avatar inverts it (sand disc, ink linework) to read as a
        // different kind of thing sitting next to the logo.
        className="w-9 h-9 rounded-full overflow-hidden flex items-center justify-center
                   ring-1 ring-surface-300 hover:ring-primary-400 transition-all"
        title={username || 'Account'}
      >
        <img
          src="/icons/judge-avatar.svg"
          alt={username || 'Account'}
          className="w-full h-full"
        />
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-52 bg-white border border-surface-300 rounded-xl shadow-lg overflow-hidden z-50">
          <div className="px-4 py-3 border-b border-surface-200 flex items-center gap-3">
            <div className="w-8 h-8 rounded-full overflow-hidden ring-1 ring-surface-300 flex items-center justify-center">
              <img src="/icons/judge-avatar.svg" alt="" className="w-full h-full" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-gray-800 truncate">
                {username || 'Guest'}
              </div>
              <div className="text-xs text-gray-400">
                {authRequired ? 'Signed in' : 'Open access'}
              </div>
            </div>
          </div>
          {authRequired && (
            <button
              onClick={() => {
                setOpen(false);
                onLogout();
              }}
              className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-gray-700 hover:bg-red-50 hover:text-red-600 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Log out
            </button>
          )}
        </div>
      )}
    </div>
  );
}
