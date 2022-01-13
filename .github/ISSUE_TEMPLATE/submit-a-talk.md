---
name: Submit a talk
about: Tell us about a talk you'd like to give
body:
- type: markdown
  attributes:
    value: >
      Thank you for your interest in talking at an Ansible community meetup !
      We are looking forward to your proposal on a wide range of Ansible topics whether you are a user, a contributor or a developer.

      If you have any questions, please feel free to reach out to us in #community:ansible.com on Matrix or #ansible-community on [libera.chat](https://libera.chat/).

- type: checkboxes
  attributes:
    label: Meetup platform
    description: >
      The Ansible community meetups will provide recorded live chat and video over [Matrix](https://matrix.org/) (bridged to [libera.chat](https://libera.chat/) on IRC) and [jitsi](https://jitsi.org/).
      Before moving forward with your proposal, we would like to make sure that you can participate and agree with this.
    options:
    - label: I can participate and agree
      required: true

- type: input
  attributes:
    label: Talk title
    description: The title of your talk
  validations:
    required: true

- type: textarea
  attributes:
    label: Talk description
    description: The description of your talk
  validations:
    required: true

- type: input
  attributes:
    label: Expected duration
    description: The expected duration of your talk
    placeholder: 10, 20 or 40 minutes including Q&A
  validations:
    required: true

- type: input
  attributes:
    label: Timezone
    description: If the proposal is accepted, we will schedule the meetup taking into consideration your availability based on your timezone.
    placeholder: UTC-5
  validations:
    required: true

- type: textarea
  attributes:
    label: Instant messaging or social media handles
    description: >
      We will promote the meetup as well as the presentations.
      Please provide your handles if you would like to be included.
...
