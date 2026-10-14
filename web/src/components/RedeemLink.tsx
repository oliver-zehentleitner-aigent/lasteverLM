import { openVoucher } from '../api/client'
import { t } from '../i18n'

/** Next to a source waiting for credit: opens the voucher dialog. */
export function RedeemLink() {
  return (
    <button type="button" className="link small redeem-link" onClick={openVoucher}>
      {t('sources.redeem')}
    </button>
  )
}
