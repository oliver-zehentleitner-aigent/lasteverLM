import { createContext, useContext } from 'react'

/** Whether the signed-in user may change anything in the admin panel
 *  (role admin); a viewer reads only, and the server answers 403 anyway. */
export const CanWriteContext = createContext(false)
export const useCanWrite = () => useContext(CanWriteContext)
