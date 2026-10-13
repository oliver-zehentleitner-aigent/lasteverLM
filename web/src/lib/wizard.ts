/** What the wizard does once the sources are in: a new notebook goes on
 *  to the output step; adding to an existing one ends here, after a note
 *  when some of the sources were in the notebook already. */
export type AfterSources = 'outputs' | 'note' | 'done'

export function afterSources(withOutputs: boolean, alreadyThere: number): AfterSources {
  if (withOutputs) return 'outputs'
  return alreadyThere > 0 ? 'note' : 'done'
}

/** The number of steps the header counts. */
export const wizardSteps = (withOutputs: boolean) => (withOutputs ? 3 : 2)
