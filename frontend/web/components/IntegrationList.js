import React, { Component } from 'react'
import _data from 'common/data/base/_data'
import ProjectStore from 'common/stores/project-store'
import ConfigProvider from 'common/providers/ConfigProvider'

const CreateEditIntegration = require('./modals/CreateEditIntegrationModal')

class Integration extends Component {
  add = () => {
    this.props.addIntegration(this.props.integration, this.props.id)
  }

  remove = (integration) => {
    this.props.removeIntegration(integration, this.props.id)
  }

  edit = (integration) => {
    this.props.editIntegration(
      this.props.integration,
      this.props.id,
      integration,
    )
  }

  render() {
    const { description, docs, image, perEnvironment } = this.props.integration
    const activeIntegrations = this.props.activeIntegrations
    const showAdd = !(
      !perEnvironment &&
      activeIntegrations &&
      activeIntegrations.length
    )
    return (
      <div className='panel panel-integrations p-4 mb-3'>
        <Flex>
          <img className='mb-2' src={image} />
          <Row space style={{ flexWrap: 'noWrap' }}>
            <div className='subtitle mt-2'>
              {description}{' '}
              {docs && (
                <Button
                  theme='text'
                  href={docs}
                  target='_blank'
                  className='fw-normal'
                >
                  View docs
                </Button>
              )}
            </div>
            <Row style={{ flexWrap: 'noWrap' }}>
              {activeIntegrations &&
                activeIntegrations.map((integration) => (
                  <Button
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      this.remove(integration)
                      return false
                    }}
                    className='ml-3'
                    theme='secondary'
                    type='submit'
                    size='xSmall'
                    key={integration.id}
                  >
                    Delete Integration
                  </Button>
                ))}
              {showAdd && (
                <Button
                  className='ml-3'
                  id='show-create-segment-btn'
                  data-test='show-create-segment-btn'
                  onClick={this.add}
                  size='xSmall'
                >
                  Add Integration
                </Button>
              )}
            </Row>
          </Row>
        </Flex>

        {activeIntegrations &&
          activeIntegrations.map((integration) => (
            <div
              key={integration.id}
              className='list-integrations clickable p-3 mt-3'
              onClick={() => this.edit(integration)}
            >
              <Row space>
                <Flex>
                  <CreateEditIntegration
                    readOnly
                    projectId={this.props.projectId}
                    data={integration}
                    integration={this.props.integration}
                  />
                </Flex>
              </Row>
            </div>
          ))}
      </div>
    )
  }
}

class IntegrationList extends Component {
  state = {}

  static contextTypes = {
    router: propTypes.object.isRequired,
  }

  componentDidMount() {
    this.fetch()
  }

  fetch = () => {
    const integrationList =
      Utils.getFlagsmithValue('integration_data') &&
      JSON.parse(Utils.getFlagsmithValue('integration_data'))
    this.setState({ isLoading: true })
    Promise.all(
      this.props.integrations.map((key) => {
        const integration = integrationList[key]
        if (integration) {
          if (integration.perEnvironment) {
            return Promise.all(
              ProjectStore.getEnvs().map((env) =>
                _data
                  .get(
                    `${Project.api}environments/${env.api_key}/integrations/${key}/`,
                  )
                  .catch(() => {}),
              ),
            ).then((res) => {
              let allItems = []
              _.each(res, (envIntegrations, index) => {
                if (envIntegrations && envIntegrations.length) {
                  allItems = allItems.concat(
                    envIntegrations.map((int) => ({
                      ...int,
                      flagsmithEnvironment:
                        ProjectStore.getEnvs()[index].api_key,
                    })),
                  )
                }
              })
              return allItems
            })
          }
          return _data
            .get(
              `${Project.api}projects/${this.props.projectId}/integrations/${key}/`,
            )
            .catch(() => {})
        }
      }),
    ).then((res) => {
      console.log(res)
      this.setState({
        activeIntegrations: _.map(res, (item) =>
          !!item && item.length ? item : [],
        ),
        isLoading: false,
      })
    })
    const params = Utils.fromParam()
    if (params && params.configure) {
      const integrationList =
        Utils.getFlagsmithValue('integration_data') &&
        JSON.parse(Utils.getFlagsmithValue('integration_data'))

      if (integrationList && integrationList[params.configure]) {
        setTimeout(() => {
          this.addIntegration(
            integrationList[params.configure],
            params.configure,
          )
          this.context.router.history.replace(document.location.pathname)
        }, 500)
      }
    }
  }

  removeIntegration = (integration, id) => {
    const env = integration.flagsmithEnvironment
      ? ProjectStore.getEnvironment(integration.flagsmithEnvironment)
      : ''
    const name = env && env.name
    openConfirm(
      'Confirm remove integration',
      <span>
        This will remove your integration from the{' '}
        {integration.flagsmithEnvironment ? 'environment ' : 'project'}
        {name ? <strong>{name}</strong> : ''}, it will no longer receive data.
        Are you sure?
      </span>,
      () => {
        if (integration.flagsmithEnvironment) {
          _data
            .delete(
              `${Project.api}environments/${integration.flagsmithEnvironment}/integrations/${id}/${integration.id}/`,
            )
            .then(this.fetch)
            .catch(this.onError)
        } else {
          _data
            .delete(
              `${Project.api}projects/${this.props.projectId}/integrations/${id}/${integration.id}/`,
            )
            .then(this.fetch)
            .catch(this.onError)
        }
      },
    )
  }

  addIntegration = (integration, id) => {
    const params = Utils.fromParam()
    openModal(
      `${integration.title} Integration`,
      <CreateEditIntegration
        id={id}
        modal
        integration={integration}
        data={
          params.environment
            ? {
                flagsmithEnvironment: params.environment,
              }
            : null
        }
        projectId={this.props.projectId}
        onComplete={this.fetch}
      />,
      'side-modal',
    )
  }

  editIntegration = (integration, id, data) => {
    openModal(
      `${integration.title} Integration`,
      <CreateEditIntegration
        id={id}
        modal
        integration={integration}
        data={data}
        projectId={this.props.projectId}
        onComplete={this.fetch}
      />,
      'p-0',
    )
  }

  render() {
    const integrationList =
      Utils.getFlagsmithValue('integration_data') &&
      JSON.parse(Utils.getFlagsmithValue('integration_data'))
    return (
      <div>
        <div>
          {this.props.integrations &&
          !this.state.isLoading &&
          this.state.activeIntegrations &&
          integrationList ? (
            this.props.integrations.map((i, index) => (
              <Integration
                addIntegration={this.addIntegration}
                editIntegration={this.editIntegration}
                removeIntegration={this.removeIntegration}
                projectId={this.props.projectId}
                id={i}
                key={i}
                activeIntegrations={this.state.activeIntegrations[index]}
                integration={integrationList[i]}
              />
            ))
          ) : (
            <div className='text-center'>
              <Loader />
            </div>
          )}
        </div>
      </div>
    )
  }
}

export default ConfigProvider(IntegrationList)
