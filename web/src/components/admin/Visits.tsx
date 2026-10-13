import { useCallback } from 'react'
import { admin } from '../../api/admin'
import type { VisitBucket } from '../../api/types'
import { t } from '../../i18n'
import { Section, Table } from './shared'
import { useLoad } from '../../hooks/useLoad'

const VISIT_DAYS = 14

export function Visits() {
  const load = useCallback(() => admin.listVisits(VISIT_DAYS), [])
  const { data, error } = useLoad<VisitBucket[]>(load, [])
  return (
    <Section title={t('adm.visits', { n: VISIT_DAYS })}>
      {error && <p className="error">{error}</p>}
      <Table head={[t('adm.col.day'), t('adm.col.path'), t('adm.col.visits'), t('adm.col.unique')]} rows={data.map((v) => [v.day, v.path, v.visits, v.unique])} />
    </Section>
  )
}
