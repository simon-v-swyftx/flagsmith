import React, { Component } from 'react'
import ChangeRequestStore from 'common/stores/change-requests-store'
import OrganisationStore from 'common/stores/organisation-store'
import FeatureListStore from 'common/stores/feature-list-store'
import withSegmentOverrides from 'common/providers/withSegmentOverrides'
import ProjectStore from 'common/stores/project-store'
import ConfigProvider from 'common/providers/ConfigProvider'
import Constants from 'common/constants'
import Button from 'components/base/forms/Button'
import UserSelect from 'components/UserSelect'
import ValueEditor from 'components/ValueEditor'
import CreateFlagModal from 'components/modals/CreateFlag'
import InfoMessage from 'components/InfoMessage'
import Permission from 'common/providers/Permission'
import JSONReference from 'components/JSONReference'
import MyGroupsSelect from 'components/MyGroupsSelect'
import { getMyGroups } from 'common/services/useMyGroup'
import { getStore } from 'common/store'
import PageTitle from 'components/PageTitle'
import Icon from 'components/Icon'

const labelWidth = 100

const ChangeRequestsPage = class extends Component {
  static displayName = 'ChangeRequestsPage'

  static contextTypes = {
    router: propTypes.object.isRequired,
  }

  getApprovals = (users, approvals) =>
    users?.filter((v) => approvals?.includes(v.group))

  getGroupApprovals = (groups, approvals) =>
    groups.filter((v) => approvals.find((a) => a.group === v.id))

  constructor(props, context) {
    super(props, context)
    this.state = {
      showArchived: false,
      tags: [],
    }
    ES6Component(this)
    this.listenTo(ChangeRequestStore, 'change', () => this.forceUpdate())
    this.listenTo(FeatureListStore, 'change', () => this.forceUpdate())
    this.listenTo(OrganisationStore, 'change', () => this.forceUpdate())
    this.listenTo(ChangeRequestStore, 'problem', () =>
      this.setState({ error: true }),
    )
    AppActions.getChangeRequest(
      this.props.match.params.id,
      this.props.match.params.projectId,
      this.props.match.params.environmentId,
    )
    AppActions.getOrganisation(AccountStore.getOrganisation().id)
    getMyGroups(getStore(), { orgId: AccountStore.getOrganisation().id }).then(
      (res) => {
        this.setState({ groups: res?.data?.results || [] })
      },
    )
  }

  removeOwner = (id, isUser = true) => {
    if (ChangeRequestStore.isLoading) return
    const changeRequest = ChangeRequestStore.model[this.props.match.params.id]
    AppActions.updateChangeRequest({
      approvals: isUser
        ? changeRequest.approvals.filter((v) => v.user !== id)
        : changeRequest.approvals,
      description: changeRequest.description,
      feature_states: changeRequest.feature_states,
      group_assignments: isUser
        ? changeRequest.group_assignments
        : changeRequest.group_assignments.filter((v) => v.group !== id),
      id: changeRequest.id,
      title: changeRequest.title,
    })
  }

  addOwner = (id, isUser = true) => {
    if (ChangeRequestStore.isLoading) return
    const changeRequest = ChangeRequestStore.model[this.props.match.params.id]
    AppActions.updateChangeRequest({
      approvals: isUser
        ? changeRequest.approvals.concat([{ user: id }])
        : changeRequest.approvals,
      description: changeRequest.description,
      feature_states: changeRequest.feature_states,
      group_assignments: isUser
        ? changeRequest.group_assignments
        : changeRequest.group_assignments.concat([{ group: id }]),
      id: changeRequest.id,
      title: changeRequest.title,
    })
  }
  componentDidMount = () => {}

  deleteChangeRequest = () => {
    openConfirm(
      'Delete Change Request',
      <div>Are you sure you want to delete this change request?</div>,
      () => {
        AppActions.deleteChangeRequest(this.props.match.params.id, () => {
          this.context.router.history.replace(
            `/project/${this.props.match.params.projectId}/environment/${this.props.match.params.environmentId}/change-requests`,
          )
        })
      },
    )
  }

  editChangeRequest = (projectFlag, environmentFlag) => {
    const id = this.props.match.params.id
    const changeRequest = ChangeRequestStore.model[id]

    openModal(
      'Edit Change Request',
      <CreateFlagModal
        isEdit
        environmentId={this.props.match.params.environmentId}
        projectId={this.props.match.params.projectId}
        changeRequest={ChangeRequestStore.model[id]}
        projectFlag={projectFlag}
        multivariate_options={
          changeRequest.feature_states[0].multivariate_feature_state_values
        }
        environmentFlag={{
          ...environmentFlag,
          enabled: changeRequest.feature_states[0].enabled,
          feature_state_value: Utils.featureStateToValue(
            changeRequest.feature_states[0].feature_state_value,
          ),
        }}
        flagId={environmentFlag.id}
      />,
      'side-modal create-feature-modal',
    )
  }

  approveChangeRequest = () => {
    AppActions.actionChangeRequest(this.props.match.params.id, 'approve')
  }

  publishChangeRequest = () => {
    const id = this.props.match.params.id
    const changeRequest = ChangeRequestStore.model[id]
    const isScheduled =
      new Date(changeRequest.feature_states[0].live_from).valueOf() >
      new Date().valueOf()
    const scheduledDate = moment(changeRequest.feature_states[0].live_from)

    openConfirm(
      `${isScheduled ? 'Schedule' : 'Publish'} Change Request`,
      <div>
        Are you sure you want to {isScheduled ? 'schedule' : 'publish'} this
        change request
        {isScheduled
          ? ` for ${scheduledDate.format('Do MMM YYYY hh:mma')}`
          : ''}
        ? This will adjust the feature for your environment.
      </div>,
      () => {
        AppActions.actionChangeRequest(
          this.props.match.params.id,
          'commit',
          () => {
            AppActions.refreshFeatures(
              this.props.match.params.projectId,
              this.props.match.params.environmentId,
              true,
            )
          },
        )
      },
    )
  }

  fetchFeature = (featureId) => {
    this.activeFeature = featureId
  }

  render() {
    const id = this.props.match.params.id
    const changeRequest = ChangeRequestStore.model[id]
    const flags = ChangeRequestStore.flags[id]
    const environmentFlag = flags && flags.environmentFlag
    const projectFlag = flags && flags.projectFlag

    if (this.state.error && !changeRequest) {
      return (
        <div
          data-test='change-requests-page'
          id='change-requests-page'
          className='app-container container'
        >
          <h3>Change Request not Found</h3>
          <p>The Change Request may have been deleted.</p>
        </div>
      )
    }
    if (
      !changeRequest ||
      OrganisationStore.isLoading ||
      !projectFlag ||
      !environmentFlag
    ) {
      return (
        <div
          data-test='change-requests-page'
          id='change-requests-page'
          className='app-container container'
        >
          <div className='text-center'>
            <Loader />
          </div>
        </div>
      )
    }
    const orgUsers = OrganisationStore.model && OrganisationStore.model.users
    const orgGroups = this.state.groups || []
    const ownerUsers =
      changeRequest &&
      this.getApprovals(
        orgUsers,
        changeRequest.approvals.map((v) => v.user),
      )
    const ownerGroups =
      changeRequest &&
      this.getGroupApprovals(orgGroups, changeRequest.group_assignments)
    const featureId =
      changeRequest &&
      changeRequest.feature_states[0] &&
      changeRequest.feature_states[0].feature
    if (featureId !== this.activeFeature) {
      this.fetchFeature(featureId)
    }
    const user =
      changeRequest && orgUsers.find((v) => v.id === changeRequest.user)
    const committedBy =
      (changeRequest.committed_by &&
        orgUsers &&
        orgUsers.find((v) => v.id === changeRequest.committed_by)) ||
      {}
    const isScheduled =
      new Date(changeRequest.feature_states[0].live_from).valueOf() >
      new Date().valueOf()
    const scheduledDate = moment(changeRequest.feature_states[0].live_from)
    const isMv =
      projectFlag &&
      projectFlag.multivariate_options &&
      !!projectFlag.multivariate_options.length

    const approval =
      changeRequest &&
      changeRequest.approvals.find((v) => v.user === AccountStore.getUser().id)
    const approvedBy = changeRequest.approvals
      .filter((v) => !!v.approved_at)
      .map((v) => {
        const matchingUser = orgUsers.find((u) => u.id === v.user) || {}
        return `${matchingUser.first_name} ${matchingUser.last_name}`
      })
    const approved = !!approval && !!approval.approved_at
    const environment = ProjectStore.getEnvironment(
      this.props.match.params.environmentId,
    )

    const minApprovals = environment.minimum_change_request_approvals || 0
    const newValue =
      changeRequest.feature_states[0] &&
      Utils.featureStateToValue(
        changeRequest.feature_states[0].feature_state_value,
      )
    const oldValue = environmentFlag && environmentFlag.feature_state_value
    const newEnabled =
      changeRequest.feature_states[0] && changeRequest.feature_states[0].enabled
    const oldEnabled = environmentFlag && environmentFlag.enabled
    let mvData = []
    let mvChanged = false
    if (isMv) {
      mvData = projectFlag.multivariate_options.map((v) => {
        const matchingOldValue =
          environmentFlag.multivariate_feature_state_values.find(
            (e) => e.multivariate_feature_option === v.id,
          )
        const matchingNewValue =
          changeRequest.feature_states[0].multivariate_feature_state_values.find(
            (e) => e.multivariate_feature_option === v.id,
          )
        if (
          matchingOldValue.percentage_allocation !==
          matchingNewValue.percentage_allocation
        ) {
          mvChanged = true
        }
        return {
          changed:
            matchingOldValue.percentage_allocation !==
            matchingNewValue.percentage_allocation,
          newValue: matchingNewValue.percentage_allocation,
          oldValue: matchingOldValue.percentage_allocation,
          value: Utils.featureStateToValue(v),
        }
      })
    }
    const isYourChangeRequest = changeRequest.user === AccountStore.getUser().id
    return (
      <Permission
        level='environment'
        permission={Utils.getApproveChangeRequestPermission(true)}
        id={this.props.match.params.environmentId}
      >
        {({ permission: approvePermission }) => (
          <Permission
            level='environment'
            permission='UPDATE_FEATURE_STATE'
            id={this.props.match.params.environmentId}
          >
            {({ permission: publishPermission }) => (
              <div
                style={{ opacity: ChangeRequestStore.isLoading ? 0.25 : 1 }}
                data-test='change-requests-page'
                id='change-requests-page'
                className='app-container container-fluid mt-1'
              >
                <nav aria-label='breadcrumb'>
                  <ol className='breadcrumb mb-2 py-1"'>
                    <li className='breadcrumb-item fs-small lh-sm'>
                      <Link
                        className='fw-normal'
                        to={`/project/${
                          this.props.match.params.projectId
                        }/environment/${
                          this.props.match.params.environmentId
                        }/${
                          isScheduled ? 'scheduled-changes' : 'change-requests'
                        }`}
                      >
                        {isScheduled ? 'Scheduling' : 'Change request'}
                      </Link>
                    </li>
                    <li
                      className='breadcrumb-item active fs-small lh-sm text-muted'
                      aria-current='page'
                      style={{ opacity: 0.6 }}
                    >
                      {changeRequest.title}
                    </li>
                  </ol>
                </nav>
                <PageTitle
                  cta={
                    <Row>
                      <Button
                        theme='secondary'
                        onClick={this.deleteChangeRequest}
                      >
                        Delete
                      </Button>
                      <Button
                        onClick={() =>
                          this.editChangeRequest(projectFlag, environmentFlag)
                        }
                        className='ml-2'
                      >
                        Edit
                      </Button>
                    </Row>
                  }
                  title={changeRequest.title}
                >
                  Created at{' '}
                  {moment(changeRequest.created_at).format(
                    'Do MMM YYYY HH:mma',
                  )}{' '}
                  by {changeRequest.user && user.first_name}{' '}
                  {user && user.last_name}
                </PageTitle>
                <p className='mt-2'>{changeRequest.description}</p>
                <div className='row'>
                  <div className='col-md-12'>
                    {isScheduled && (
                      <div className='col-md-6 mb-4'>
                        <InfoMessage
                          icon='ion-md-calendar'
                          title='Scheduled Change'
                        >
                          This feature change{' '}
                          {changeRequest?.committedAt
                            ? 'is scheduled to'
                            : 'will'}{' '}
                          go live at{' '}
                          {scheduledDate.format('Do MMM YYYY hh:mma')}
                          {changeRequest?.committed_at
                            ? ' unless it is edited or deleted'
                            : ' if it is approved and published'}
                          .
                          {!!changeRequest?.committedAt &&
                            'You can still edit / remove the change request before this date.'}
                        </InfoMessage>
                      </div>
                    )}
                    <InputGroup
                      className='col-md-6'
                      component={
                        <>
                          {!Utils.getFlagsmithHasFeature(
                            'disable_users_as_reviewers',
                          ) && (
                            <div className='mb-4'>
                              <Row
                                onClick={() =>
                                  this.setState({ showUsers: true })
                                }
                                className='font-weight-medium clickable'
                              >
                                <div className='mr-2'>Assigned users</div>
                                <Icon
                                  name='setting'
                                  width={20}
                                  fill='#656D7B'
                                />
                              </Row>
                              <Row className='mt-2'>
                                {ownerUsers.length !== 0 &&
                                  ownerUsers.map((u) => (
                                    <Row
                                      key={u.id}
                                      onClick={() => this.removeOwner(u.id)}
                                      className='chip'
                                      style={{
                                        marginBottom: 4,
                                        marginTop: 4,
                                      }}
                                    >
                                      <span className='font-weight-bold'>
                                        {u.first_name} {u.last_name}
                                      </span>
                                      <span className='chip-icon ion ion-ios-close' />
                                    </Row>
                                  ))}
                              </Row>
                              <UserSelect
                                users={orgUsers}
                                value={
                                  ownerUsers && ownerUsers.map((v) => v.id)
                                }
                                onAdd={this.addOwner}
                                onRemove={this.removeOwner}
                                isOpen={this.state.showUsers}
                                onToggle={() =>
                                  this.setState({
                                    showUsers: !this.state.showUsers,
                                  })
                                }
                              />
                            </div>
                          )}
                          {Utils.getFlagsmithHasFeature(
                            'enable_groups_as_reviewers',
                          ) && (
                            <div className='mb-4'>
                              <Row
                                onClick={() =>
                                  this.setState({ showGroups: true })
                                }
                                className='font-weight-medium clickable'
                              >
                                <div className='mr-2'>Assigned groups</div>
                                <Icon
                                  name='setting'
                                  width={20}
                                  fill='#656D7B'
                                />
                              </Row>
                              <Row className='mt-2'>
                                {!!ownerGroups?.length &&
                                  ownerGroups.map((g) => (
                                    <Row
                                      key={g.id}
                                      onClick={() =>
                                        this.removeOwner(g.id, false)
                                      }
                                      className='chip'
                                      style={{
                                        marginBottom: 4,
                                        marginTop: 4,
                                      }}
                                    >
                                      <span className='font-weight-bold'>
                                        {g.name}
                                      </span>
                                      <span className='chip-icon ion ion-ios-close' />
                                    </Row>
                                  ))}
                              </Row>
                              <MyGroupsSelect
                                orgId={AccountStore.getOrganisation().id}
                                groups={orgGroups}
                                value={
                                  ownerGroups && ownerGroups.map((v) => v.id)
                                }
                                onAdd={this.addOwner}
                                onRemove={this.removeOwner}
                                isOpen={this.state.showGroups}
                                onToggle={() =>
                                  this.setState({
                                    showGroups: !this.state.showGroups,
                                  })
                                }
                              />
                            </div>
                          )}
                        </>
                      }
                    />
                    <Panel
                      title={
                        isScheduled ? 'Scheduled Change' : 'Change Request'
                      }
                      className='no-pad'
                    >
                      <div className='search-list'>
                        <Row className='list-item change-request-item px-4'>
                          <div
                            className='font-weight-medium mr-3'
                            style={{ width: labelWidth }}
                          >
                            Feature:
                          </div>

                          <a
                            target='_blank'
                            className='btn-link font-weight-medium'
                            href={`/project/${
                              this.props.match.params.projectId
                            }/environment/${
                              this.props.match.params.environmentId
                            }/features?feature=${
                              projectFlag && projectFlag.id
                            }`}
                            rel='noreferrer'
                          >
                            {projectFlag && projectFlag.name}
                          </a>
                        </Row>
                        <Row
                          className='list-item change-request-item px-4'
                          style={{
                            opacity:
                              newEnabled === oldEnabled &&
                              !changeRequest.committed_at
                                ? 0.25
                                : 1,
                          }}
                        >
                          <div
                            className='font-weight-medium mr-3'
                            style={{ width: labelWidth }}
                          >
                            Enabled:
                          </div>
                          {!changeRequest.committed_at && (
                            <Flex className='flex-row'>
                              <Switch checked={oldEnabled} />
                              <div className='ml-3'>Live Version</div>
                            </Flex>
                          )}
                          <Flex className='flex-row'>
                            <Switch checked={newEnabled} />
                            <div className='ml-3'>
                              {isScheduled
                                ? 'Scheduled Change'
                                : 'Change Request'}
                            </div>
                          </Flex>
                        </Row>
                        <Row
                          className='list-item change-request-item px-4'
                          style={{
                            opacity:
                              oldValue === newValue &&
                              !changeRequest.committed_at
                                ? 0.25
                                : 1,
                          }}
                        >
                          <div
                            className='font-weight-medium mr-3'
                            style={{ width: labelWidth }}
                          >
                            Value:
                          </div>
                          {!changeRequest.committed_at && (
                            <Flex className='mr-4'>
                              <label>Scheduled Change</label>
                              <ValueEditor
                                value={Utils.getTypedValue(oldValue)}
                                className='code-medium'
                              />
                            </Flex>
                          )}
                          <Flex
                            style={{
                              maxWidth: changeRequest.committed_at
                                ? '445px'
                                : '',
                            }}
                          >
                            <label>Scheduled Change</label>
                            <ValueEditor
                              value={newValue}
                              className='code-medium'
                            />
                          </Flex>
                        </Row>
                        {isMv && (
                          <Row
                            className='list-item px-4 align-start change-request-item'
                            style={{
                              opacity:
                                !mvChanged && !changeRequest.committed_at
                                  ? 0.25
                                  : 1,
                            }}
                          >
                            <div
                              className='font-weight-medium mr-3'
                              style={{ width: labelWidth }}
                            >
                              Variations:
                            </div>

                            <Flex className='mr-2'>
                              {mvData.map((v, i) => (
                                <div
                                  key={i}
                                  className='mb-3'
                                  style={{
                                    opacity: mvChanged && !v.changed ? 0.25 : 1,
                                  }}
                                >
                                  <Flex>
                                    <label>Variation {i + 1}</label>
                                    <ValueEditor
                                      value={Utils.getTypedValue(v.value)}
                                      className='code-medium'
                                    />
                                  </Flex>
                                  <Row>
                                    <Flex className='mr-4 mt-1'>
                                      <span className='fs-small lh-sm text-muted'>
                                        Environment weight: {v.oldValue}%
                                      </span>
                                    </Flex>

                                    <Flex className='mt-1'>
                                      <span className='fs-small lh-sm text-muted'>
                                        Environment weight: {v.newValue}%
                                      </span>
                                    </Flex>
                                  </Row>
                                </div>
                              ))}
                            </Flex>
                          </Row>
                        )}
                      </div>
                    </Panel>
                  </div>
                </div>
                <JSONReference
                  className='mt-4'
                  title={'Change Request'}
                  json={ChangeRequestStore.model?.[id]}
                />
                <Row className='mt-4'>
                  <Flex>
                    {approvedBy.length ? (
                      <div className='text-right mb-2 mr-2 font-weight-medium'>
                        Approved by {approvedBy.join(', ')}
                      </div>
                    ) : (
                      !!minApprovals && (
                        <div className='text-right mb-2 mr-2 font-weight-medium'>
                          You need at least {minApprovals} approval
                          {minApprovals !== 1 ? 's' : ''} to{' '}
                          {isScheduled ? 'schedule' : 'publish'} this change
                        </div>
                      )
                    )}

                    {changeRequest.committed_at ? (
                      <div className='text-right mr-2 font-weight-medium'>
                        Committed at{' '}
                        {moment(changeRequest.committed_at).format(
                          'Do MMM YYYY HH:mma',
                        )}{' '}
                        by {committedBy.first_name} {committedBy.last_name}
                      </div>
                    ) : (
                      <Row className='text-right'>
                        <Flex />
                        {!isYourChangeRequest &&
                          Utils.renderWithPermission(
                            approvePermission,
                            Constants.environmentPermissions(
                              'Approve Change Requests',
                            ),
                            <Button
                              disabled={approved || !approvePermission}
                              onClick={this.approveChangeRequest}
                              theme='secondary'
                            >
                              {approved ? 'Approved' : 'Approve'}
                            </Button>,
                          )}
                        {Utils.renderWithPermission(
                          publishPermission,
                          Constants.environmentPermissions(
                            'Update Feature States',
                          ),
                          <Button
                            disabled={
                              approvedBy.length < minApprovals ||
                              !publishPermission
                            }
                            onClick={this.publishChangeRequest}
                            className='btn ml-2'
                          >
                            {isScheduled ? 'Publish Scheduled' : 'Publish'}{' '}
                            Change
                          </Button>,
                        )}
                      </Row>
                    )}
                  </Flex>
                </Row>

                <Row>
                  <div style={{ minHeight: 300 }} />
                </Row>
              </div>
            )}
          </Permission>
        )}
      </Permission>
    )
  }
}

ChangeRequestsPage.propTypes = {}

module.exports = ConfigProvider(withSegmentOverrides(ChangeRequestsPage))
