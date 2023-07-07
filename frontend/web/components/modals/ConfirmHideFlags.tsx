import React, { FC, FormEvent, useState } from 'react'
import ModalHR from './ModalHR'
import Button from 'components/base/forms/Button'
import { Project } from 'common/types/responses'
import InputGroup from 'components/base/forms/InputGroup'
import Utils from 'common/utils/utils' // we need this to make JSX compile

type ConfirmHideFlagsType = {
  project: Project
  cb: () => void
  value: boolean
}

const ConfirmHideFlags: FC<ConfirmHideFlagsType> = ({ cb, project, value }) => {
  const [challenge, setChallenge] = useState()

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (challenge == project.name) {
      closeModal()
      cb()
    }
  }
  return (
    <form onSubmit={submit}>
      <div className='modal-body'>
        <p>
          This will <strong>{value ? 'show' : 'hide'}</strong> disabled flags
          for <strong>all environments</strong> within the project{' '}
          <strong>{project.name}</strong>.
        </p>
        <InputGroup
          data-test='js-project-name'
          inputProps={{ className: 'full-width' }}
          className='mb-0'
          title='Please type the project name to confirm'
          placeholder='Project name'
          onChange={(e: InputEvent) =>
            setChallenge(Utils.safeParseEventValue(e))
          }
        />
      </div>
      <ModalHR />
      <div className='modal-footer'>
        <Button onClick={closeModal} className='me-2' theme='secondary'>
          Cancel
        </Button>
        <Button
          type='submit'
          data-test='js-confirm'
          disabled={challenge != project.name}
        >
          Confirm
        </Button>
      </div>
    </form>
  )
}

export default ConfirmHideFlags
