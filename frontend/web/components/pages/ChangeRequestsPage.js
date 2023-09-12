import React, { Component } from 'react'
import ChangeRequestStore from 'common/stores/change-requests-store'
import OrganisationStore from 'common/stores/organisation-store'
import ProjectStore from 'common/stores/project-store'
import ConfigProvider from 'common/providers/ConfigProvider'
import PaymentModal from 'components/modals/Payment'
import Tabs from 'components/base/forms/Tabs'
import TabItem from 'components/base/forms/TabItem'
import JSONReference from 'components/JSONReference'
import InfoMessage from 'components/InfoMessage'
import Icon from 'components/Icon'
import PageTitle from 'components/PageTitle'

const ChangeRequestsPage = class extends Component {
  static displayName = 'ChangeRequestsPage'

  static contextTypes = {
    router: propTypes.object.isRequired,
  }

  constructor(props, context) {
    super(props, context)
    this.state = {
      live_after: new Date().toISOString(),
      showArchived: false,
      tags: [],
    }
    ES6Component(this)
    this.listenTo(ChangeRequestStore, 'change', () => this.forceUpdate())
    this.listenTo(OrganisationStore, 'change', () => this.forceUpdate())
  }
  componentDidMount = () => {
    AppActions.getChangeRequests(this.props.match.params.environmentId, {})
    AppActions.getChangeRequests(this.props.match.params.environmentId, {
      committed: true,
    })
    AppActions.getChangeRequests(this.props.match.params.environmentId, {
      live_from_after: this.state.live_after,
    })
    AppActions.getOrganisation(AccountStore.getOrganisation().id)
  }

  render() {
    const { environmentId, projectId } = this.props.match.params
    const data =
      ChangeRequestStore.model &&
      ChangeRequestStore.model[environmentId] &&
      ChangeRequestStore.model[environmentId] &&
      ChangeRequestStore.model[environmentId].results
    const dataPaging =
      ChangeRequestStore.model &&
      ChangeRequestStore.model[environmentId] &&
      ChangeRequestStore.model[environmentId] &&
      ChangeRequestStore.model[environmentId]

    const dataClosed =
      ChangeRequestStore.committed &&
      ChangeRequestStore.committed[environmentId] &&
      ChangeRequestStore.committed[environmentId].results
    const dataClosedPaging =
      ChangeRequestStore.committed &&
      ChangeRequestStore.committed[environmentId] &&
      ChangeRequestStore.committed[environmentId]

    const environment = ProjectStore.getEnvironment(environmentId)

    const has4EyesPermission = Utils.getPlansPermission('4_EYES')
    return (
      <div
        data-test='change-requests-page'
        id='change-requests-page'
        className='app-container container'
      >
        <PageTitle title={'Change Requests'}>
          View and manage proposed feature state changes.
        </PageTitle>
        <Flex>
          {!has4EyesPermission ? (
            <div className='mt-2'>
              <InfoMessage>
                View and manage your feature changes with a Change Request flow
                with our{' '}
                <Button
                  theme='text'
                  onClick={() => {
                    openModal(
                      'Payment plans',
                      <PaymentModal viewOnly={false} />,
                      'modal-lg',
                    )
                  }}
                >
                  Scale-up plan
                </Button>
                . Find out more{' '}
                <Button
                  theme='text'
                  href='https://docs.flagsmith.com/advanced-use/change-requests'
                  target='_blank'
                  rel='noreferrer'
                >
                  here
                </Button>
                .
              </InfoMessage>
            </div>
          ) : (
            <div>
              <p>
                {environment &&
                !Utils.changeRequestsEnabled(
                  environment.minimum_change_request_approvals,
                ) ? (
                  <InfoMessage>
                    To enable this feature set a minimum number of approvals in{' '}
                    <Link
                      to={`/project/${projectId}/environment/${environmentId}/settings`}
                    >
                      Environment Settings
                    </Link>
                  </InfoMessage>
                ) : null}
              </p>
              <Tabs
                value={this.state.tab}
                onChange={(tab) => {
                  this.setState({ tab })
                }}
              >
                <TabItem
                  tabLabel={
                    <span className='flex-row justify-content-center'>
                      Open
                      {data && !!dataPaging.count && (
                        <div className='counter-value ml-1'>
                          {dataPaging.count}
                        </div>
                      )}
                    </span>
                  }
                >
                  <PanelSearch
                    renderSearchWithNoResults
                    id='users-list'
                    title='Change Requests'
                    className='mt-4 no-pad'
                    isLoading={
                      ChangeRequestStore.isLoading ||
                      !data ||
                      !OrganisationStore.model
                    }
                    items={data}
                    paging={dataPaging}
                    nextPage={() =>
                      AppActions.getChangeRequests(
                        this.props.match.params.environmentId,
                        {},
                        dataPaging.next,
                      )
                    }
                    prevPage={() =>
                      AppActions.getChangeRequests(
                        this.props.match.params.environmentId,
                        {},
                        dataPaging.previous,
                      )
                    }
                    goToPage={(page) =>
                      AppActions.getChangeRequests(
                        this.props.match.params.environmentId,
                        {},
                        `${Project.api}environments/${environmentId}/list-change-requests/?page=${page}`,
                      )
                    }
                    renderFooter={() => (
                      <JSONReference
                        className='mt-4 ml-3'
                        title={'Change Requests'}
                        json={data}
                      />
                    )}
                    renderRow={({
                      created_at,
                      id,
                      live_from,
                      title,
                      user: _user,
                    }) => {
                      const user =
                        (OrganisationStore.model &&
                          OrganisationStore.model.users &&
                          OrganisationStore.model.users.find(
                            (v) => v.id === _user,
                          )) ||
                        {}
                      const isScheduled =
                        new Date(live_from).valueOf() > new Date().valueOf()
                      return (
                        <Link
                          to={`/project/${projectId}/environment/${environmentId}/change-requests/${id}`}
                          className='flex-row list-item clickable'
                        >
                          <Flex className='table-column px-3'>
                            <div className='font-weight-medium'>
                              {title}
                              {isScheduled && (
                                <span className='ml-1 mr-4 ion ion-md-time' />
                              )}
                            </div>
                            <div className='list-item-subtitle mt-1'>
                              Created at{' '}
                              {moment(created_at).format('Do MMM YYYY HH:mma')}{' '}
                              by {user && user.first_name}{' '}
                              {user && user.last_name}
                            </div>
                          </Flex>
                          <div className='table-column'>
                            <Icon
                              name='chevron-right'
                              fill='#9DA4AE'
                              width={20}
                            />
                          </div>
                        </Link>
                      )
                    }}
                  />
                </TabItem>
                <TabItem
                  tabLabel={
                    <span className='flex-row justify-content-center'>
                      Closed
                    </span>
                  }
                >
                  <PanelSearch
                    renderSearchWithNoResults
                    id='users-list'
                    title='Change Requests'
                    className='mt-4 no-pad'
                    isLoading={
                      ChangeRequestStore.isLoading ||
                      !data ||
                      !OrganisationStore.model
                    }
                    items={dataClosed}
                    paging={dataClosedPaging}
                    nextPage={() =>
                      AppActions.getChangeRequests(
                        this.props.match.params.environmentId,
                        { committed: true },
                        dataPaging.next,
                      )
                    }
                    prevPage={() =>
                      AppActions.getChangeRequests(
                        this.props.match.params.environmentId,
                        { committed: true },
                        dataPaging.previous,
                      )
                    }
                    goToPage={(page) =>
                      AppActions.getChangeRequests(
                        this.props.match.params.environmentId,
                        { committed: true },
                        `${Project.api}environments/${environmentId}/list-change-requests/?page=${page}`,
                      )
                    }
                    renderFooter={() => (
                      <JSONReference
                        className='mt-4 ml-3'
                        title={'Change Requests'}
                        json={dataClosed}
                      />
                    )}
                    renderRow={({ created_at, id, title, user: _user }) => {
                      const user =
                        OrganisationStore.model &&
                        OrganisationStore.model.users.find(
                          (v) => v.id === _user,
                        )
                      return (
                        <Link
                          to={`/project/${projectId}/environment/${environmentId}/change-requests/${id}`}
                          className='flex-row list-item clickable'
                        >
                          <Flex className='table-column px-3'>
                            <div className='font-weight-medium'>{title}</div>
                            <div className='list-item-subtitle mt-1'>
                              Live from{' '}
                              {moment(created_at).format('Do MMM YYYY HH:mma')}{' '}
                              by {user && user.first_name}{' '}
                              {user && user.last_name}
                            </div>
                          </Flex>
                          <div className='table-column'>
                            <Icon
                              name='chevron-right'
                              fill='#9DA4AE'
                              width={20}
                            />
                          </div>
                        </Link>
                      )
                    }}
                  />
                </TabItem>
              </Tabs>
            </div>
          )}
        </Flex>
      </div>
    )
  }
}

ChangeRequestsPage.propTypes = {}

module.exports = ConfigProvider(ChangeRequestsPage)
