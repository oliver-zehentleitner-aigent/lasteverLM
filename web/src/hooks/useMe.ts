import { createContext, useContext } from 'react'
import type { User } from '../api/types'

/** The signed-in user, for the places that read preferences, and the
 *  setter the settings page uses after saving them. */
export const MeContext = createContext<{ me: User | null; setMe: (u: User) => void }>({ me: null, setMe: () => {} })

export function useMe() {
  return useContext(MeContext)
}
