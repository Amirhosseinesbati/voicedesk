import type { components } from './openapi.generated'
import type {
  Appointment,
  AuthResponse,
  Availability,
  ConfirmResponse,
  CreateProposalInput,
  Handoff,
  Proposal,
  ProposalResponse,
  Session,
  TranscriptTurn,
  TurnResponse,
  WorkspaceConfig,
} from './types'

type ApiSchema = components['schemas']
type Assignable<Actual, Contract> = [Actual] extends [Contract] ? true : false
type Expect<Condition extends true> = Condition

// Compilation fails when a UI/client shape drifts from its generated API schema.
export type ApiContractChecks = [
  Expect<Assignable<AuthResponse, ApiSchema['AuthView']>>,
  Expect<Assignable<Session, ApiSchema['SessionView']>>,
  Expect<Assignable<TranscriptTurn, ApiSchema['TurnView']>>,
  Expect<Assignable<Proposal, ApiSchema['ProposalView']>>,
  Expect<Assignable<ProposalResponse, ApiSchema['ProposalResult']>>,
  Expect<Assignable<TurnResponse, ApiSchema['TurnResult']>>,
  Expect<Assignable<CreateProposalInput, ApiSchema['ProposalInput']>>,
  Expect<Assignable<Availability, ApiSchema['AvailabilityView']>>,
  Expect<Assignable<Appointment, ApiSchema['AppointmentView']>>,
  Expect<Assignable<ConfirmResponse, ApiSchema['AppointmentResult']>>,
  Expect<Assignable<Handoff, ApiSchema['HandoffView']>>,
  Expect<Assignable<WorkspaceConfig, ApiSchema['WorkspaceView']>>,
  Expect<Assignable<Omit<WorkspaceConfig, 'id' | 'policy_review_required'>, ApiSchema['WorkspaceInput']>>,
]
