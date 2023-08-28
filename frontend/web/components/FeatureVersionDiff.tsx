import { FC } from 'react'
import FeatureDiff from './FeatureDiff'
import { useGetVersionFeatureStateQuery } from 'common/services/useVersionFeatureState'
type VersionDiffType = {
  oldUUID: string
  newUUID: string
  environmentId: string
  featureId: string
}

const FeatureVersionDiff: FC<VersionDiffType> = ({
  environmentId,
  featureId,
  newUUID,
  oldUUID,
}) => {
  const { data: oldData } = useGetVersionFeatureStateQuery({
    environmentId,
    featureId,
    sha: oldUUID,
  })
  const { data: newData } = useGetVersionFeatureStateQuery({
    environmentId,
    featureId,
    sha: newUUID,
  })
  return (
    <div className='p-2'>
      {!oldData || !newData ? (
        <div className='text-center'>
          <Loader />
        </div>
      ) : (
        <FeatureDiff oldState={oldData} newState={newData} />
      )}
    </div>
  )
}

export default FeatureVersionDiff
