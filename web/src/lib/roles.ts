import type { User, UserRole } from '../api/types'

/** The user's role; an account service without roles only says is_admin. */
export function roleOf(u: Pick<User, 'role' | 'is_admin'>): UserRole {
  return u.role ?? (u.is_admin ? 'admin' : 'user')
}

/** Viewers and admins see the admin panel; only admins change anything there. */
export const canSeeAdmin = (u: Pick<User, 'role' | 'is_admin'> | null | undefined) => !!u && roleOf(u) !== 'user'
export const canWriteAdmin = (u: Pick<User, 'role' | 'is_admin'> | null | undefined) => !!u && roleOf(u) === 'admin'

export const ROLES: readonly UserRole[] = ['user', 'viewer', 'admin']
