# Prompt 3: Structured + UML

You are building a backend application. Read the following information for the full requirements and produce a complete, working implementation. Produce the complete application as downloadable Python files, one per module, including a dependency file. Do not ask clarifying questions; make reasonable decisions and proceed.

Build the application in Python using the FastAPI framework, with SQLite for storage. Use only widely available libraries. Do not use any external payment service.

The application must expose exactly the following endpoints, using these paths, these request field names, and these response field names. All request and response bodies are JSON. All monetary values are integers representing pence.

Endpoints (all request/response bodies are JSON; all amounts are integer pence):

POST /auth/register   — request: email, password   — response: user_id, email   — 201\
POST /auth/login      — request: email, password   — response: access_token    — 200\
GET  /accounts/me     — response: account_id, balance_pence, currency          — 200\
POST /deposits        — request: amount_pence       — response: transaction_id, status, balance_pence — 201\
POST /withdrawals     — request: amount_pence       — response: transaction_id, status, balance_pence — 201\
POST /transfers       — request: recipient_email, amount_pence — response: transaction_id, status, balance_pence — 201\
GET  /transactions    — response: list of { transaction_id, type, amount_pence, direction, status, created_at } — 200\
POST /transactions/{transaction_id}/reversal — response: transaction_id, reverses_transaction_id, status — 201

Authenticated endpoints expect the credential returned by /auth/login in an Authorization header as a bearer token.

The table above covers successful requests only. How the application responds to invalid, unauthorised or rejected requests is for you to decide.

Requirements:

1.	Overview
   
A peer-to-peer payments wallet. Registered users hold a balance, deposit and withdraw funds, transfer funds to one another, view their own transaction history, and reverse transfers made in error. All balances are recorded on a double-entry ledger.

2.	 Actors
   
Unauthenticated user. May register an account and log in. Has no other access. \
Registered user. Holds exactly one account. May view their balance, deposit, withdraw, transfer to another registered user, view their own transaction history, and reverse a completed transfer. 

3.	Domain entities
   
User. Identified by an email address, which is unique. Holds a stored password credential and a creation timestamp.\
Account. Belongs to exactly one user. Each user has exactly one account. Denominated in GBP.\
Transaction. A single movement of value. Has a type, which is one of deposit, withdrawal, transfer or reversal; a status, which is one of completed or reversed; a creation timestamp; and, where the transaction is a reversal, a reference to the transaction it reverses.\
Ledger entry. A single line of the ledger. Belongs to exactly one transaction and exactly one account, and records an amount in pence and a direction, which is either debit or credit.\
System account. A single internal account representing funds held outside the application. It is not owned by any user and is not directly accessible to any user.

4.	Functional requirements
   
FR1. The system shall allow a visitor to register using an email address and a password. Registration shall create one user and one account.\
FR2. The system shall allow a registered user to authenticate using their email address and password and shall issue a credential used to authorise subsequent requests.\
FR3. The system shall allow an authenticated user to retrieve the current balance of their own account.\
FR4. The system shall allow an authenticated user to deposit a specified amount into their own account.\
FR5. The system shall allow an authenticated user to withdraw a specified amount from their own account.\
FR6. The system shall allow an authenticated user to transfer a specified amount to another registered user, identified by email address.\
FR7. The system shall allow an authenticated user to retrieve the transaction history of their own account.\
FR8. The system shall allow an authenticated user to reverse a completed transfer in which they were the sending party.

5.	Business rules
   
BR1. A transfer shall be rejected if the sender's current balance is less than the transfer amount.\
BR2. A withdrawal shall be rejected if the user's current balance is less than the withdrawal amount.\
BR3. The combined value of all transfers and withdrawals made by a user shall not exceed £1,000 within any rolling 24-hour period. The window is measured backwards from the moment the request is made and is not reset at a fixed time of day. Deposits do not count towards this limit.\
BR4. Every transaction shall record exactly two ledger entries: one debit and one credit, of equal value, against two different accounts. The sum of all ledger entries in the system shall therefore always be zero.\
BR5. A deposit shall record a debit against the system account and a credit against the user's account. A withdrawal shall record a debit against the user's account and a credit against the system account.\
BR6. An account balance shall be derived from the sum of that account's ledger entries. It shall not be held as a separately maintained field that is updated in place.\
BR7. A reversal shall be affected by creating a new transaction of type reversal, which records ledger entries moving the original value in the opposite direction. The original transaction shall be marked as reversed. No existing transaction or ledger entry shall be deleted or amended.\
BR8. Only a transfer with status completed may be reversed, and only once. Deposits, withdrawals and reversals shall not be reversible.\
BR9. A user shall not transfer funds to their own account.\
BR10. A transfer shall be rejected if the specified recipient email address does not belong to a registered user.\
BR11. Deposit, withdrawal and transfer amounts shall be positive whole numbers of pence. Zero, negative, fractional and non-numeric amounts shall be rejected.\

6.	Non-functional Requirements
   
NFR1. Passwords shall be stored using a one-way hash with a per-user salt. Passwords shall not be recoverable from stored data and shall not appear in any response or log.\
NFR2. All endpoints other than registration and login shall require a valid authentication credential.\
NFR3. An authenticated user shall be able to read and act upon their own account and their own transactions only. Supplying an identifier belonging to another user shall not grant access to that user's data, whether or not the requesting user is authenticated.\
NFR4. All monetary input shall be validated before use. Values that are negative, zero, non-numeric, fractional, or outside the representable range shall be rejected without altering any account.\
NFR5. The ledger entries belonging to a single transaction shall be written as a single atomic unit. A failure occurring part-way through a transaction shall leave no partial record and shall not change any balance.

7.	Constraints
   
Monetary values shall be represented as integer pence throughout the application, in storage, in processing and in responses. Floating-point representation of monetary values shall not be used.\
The application shall support GBP only.\
External payment processing is out of scope. Deposits and withdrawals shall be treated as having been authorised elsewhere, and shall be recorded against the system account without any external call.

The following UML diagrams describe the same design:

Class UML:
@startuml
skinparam classAttributeIconSize 0

class User {
  user_id
  email
  password_hash
  created_at
}

class Account {
  account_id
  currency
  
  balance() : derived from ledger entries
}

class Transaction {
  transaction_id
  type : deposit | withdrawal | transfer | reversal
  status : completed | reversed
  created_at
  reverses_transaction_id
}

class LedgerEntry {
  ledger_entry_id
  amount_pence
  direction : debit | credit
}

User "1" -- "1" Account : owns
Account "1" -- "0..*" LedgerEntry : has
Transaction "1" -- "2" LedgerEntry : records
Transaction "0..1" -- "0..1" Transaction : reverses

note bottom of Account
  One account per user.
  A separate system account
  is the counterparty for
  deposits and withdrawals.
end note
@enduml

Use case UML:
@startuml
left to right direction
skinparam packageStyle rectangle

actor "Unauthenticated User" as visitor
actor "Registered User" as user

rectangle "Payments Wallet" {
  usecase "Register" as UC1
  usecase "Log in" as UC2
  usecase "View balance" as UC3
  usecase "Deposit funds" as UC4
  usecase "Withdraw funds" as UC5
  usecase "Transfer funds" as UC6
  usecase "View transaction history" as UC7
  usecase "Reverse a transfer" as UC8
}

visitor --> UC1
visitor --> UC2

user --> UC3
user --> UC4
user --> UC5
user --> UC6
user --> UC7
user --> UC8
@enduml

Sequence diagram UML:
@startuml
actor "Registered User" as user
participant "System" as system
database "Ledger" as ledger

user -> system : transfer(recipient_email, amount_pence)
activate system

system -> system : authenticate user
system -> system : validate amount

system -> ledger : look up recipient by email
activate ledger
ledger --> system : recipient account
deactivate ledger

alt recipient not found
  system --> user : rejected (unknown recipient)
end

system -> ledger : read sender's ledger entries
activate ledger
ledger --> system : current balance
deactivate ledger

alt balance < amount
  system --> user : rejected (insufficient funds)
end

system -> ledger : read sender's transfers and withdrawals in last 24h
activate ledger
ledger --> system : total in window
deactivate ledger

alt total + amount > daily limit
  system --> user : rejected (limit exceeded)
end

system -> ledger : write transaction with two ledger entries (atomic)
activate ledger
ledger --> system : confirmed
deactivate ledger

system --> user : success (transaction_id, status, new balance)
deactivate system
@enduml

Activity diagram UML:
@startuml
start

:Transaction requested;

switch (Transaction type?)
case (Deposit)
  :Debit system account;
  :Credit user account;
case (Withdrawal)
  :Debit user account;
  :Credit system account;
case (Transfer)
  :Debit sender;
  :Credit recipient;
endswitch

:Write both ledger entries as one atomic unit;
:Mark transaction completed;

note right
  A completed transaction is final.
  It is never deleted or edited.
end note

if (Reversal requested?) then (yes)

  if (Original is a completed transfer?) then (no)
    :Reject — only completed transfers\ncan be reversed;
    stop
  endif

  if (Already reversed?) then (yes)
    :Reject — a transfer can only\nbe reversed once;
    stop
  endif

  :Create new reversal transaction;
  :Write reversing entries\n(opposite direction);
  :Mark original transaction reversed;
  :Return success;
  stop

else (no)
  :Remains completed;
  stop
endif
@enduml



