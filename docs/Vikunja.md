---
id: untitled
doc_type: note
owner: kent
status: draft
last_updated: 2026-04-01
tags: []
---

# Vikunja integration improvements

The implementation of Vikunja isn't yet useful for viewing, managing, and changing the state of tasks.

Current state:
- "Current tasks" view shows all tasks. I'm not clear what the native purpose of the Current tasks view is. High level goals are listed with incidental and repeating tasks. The view may intend to show all open tasks in which case it is fulfilling its purpose.
- Projects such as Today, Upcoming, Overdue, Everyday, Someday, and all the other projects except for the Inbox, Goals, and Habits are empty. After reading the docs it became clear that Projects are for grouping like tasks together but Filters are what need to be used for Today, Upcoming, Overdue, and Someday. Here's the key excerpt:

  "**Projects vs. saved filters:** A project holds tasks. A [saved filter](https://vikunja.io/help/saved-filters) is a personal view that shows matching tasks from across all your projects. If you want to group tasks, use a project. If you want to see tasks from multiple projects in one place, use a saved filter."
- I notice Tasks have many features available on them.
	- Set Date Due
	- Set Start Date
	- Set End Date
	- Set Repeating Interval
	- Set Priority
	- Set Progress (%)

- Tasks can have relationships to each other and can be hierarchical. This sounds like it would very helpful for relating big goals to specific outcomes to tasks in a granular cascade. Here is the full list from the docs (https://vikunja.io/help/task-relations/):
  
## Task Relations ##

Link tasks together with relations like subtask, blocking, related, and more. 

Task relations let you create links between [tasks](https://vikunja.io/help/tasks) to express dependencies, hierarchies, or other connections. You can add relations from the right sidebar of the task detail view.

## Adding a relation[#](https://vikunja.io/help/task-relations/#adding-a-relation)

1. Open a task and scroll to the **Relations** section in the right sidebar.
2. Click **Add a relation**.
3. Search for the task you want to link to.
4. Choose the relation type from the dropdown.

![Relation type dropdown with available options](https://vikunja.io/_astro/relations-type-dropdown-dark.DqFSooQv_Z1yDV51.png)

The relation is applied immediately. The linked task will show the opposite relation automatically. For example, if you mark “Order new furniture” as **blocking** “Set up meeting rooms”, “Set up meeting rooms” will show that it is **blocked by** “Order new furniture”.

## Available relation types[#](https://vikunja.io/help/task-relations/#available-relation-types)

|Type|Description|Opposite|
|---|---|---|
|**Subtask**|The task is a subtask of the other task.|Parent task|
|**Parent task**|The task is a parent task of the other task.|Subtask|
|**Related**|Both tasks are related to each other. The connection is not further specified.|Related|
|**Duplicate of**|The task is a duplicate of the other task.|Duplicates|
|**Duplicates**|The task duplicates the other task.|Duplicate of|
|**Blocking**|The task is blocking the other task.|Blocked by|
|**Blocked by**|The task is blocked by the other task.|Blocking|
|**Precedes**|The task comes before the other task.|Follows|
|**Follows**|The task comes after the other task.|Precedes|
|**Copied from**|The task was copied from the other task.|Copied to|
|**Copied to**|The task was copied to the other task.|Copied fro|

- This would suggest that determining how a task should be added to Vikunja is a real skill considering a wide range of factors such as
	- What is the general scope of this task?
	- Does it belong in a hierarchy within a goal?
	- What project is the task related to, if any?
	- How much time might it take to complete this task?
	- When should this task begin so it can be finished on time?
	- Does this task need more than one work session to complete?
	- Is this task blocking any other tasks?
	- Are any other tasks blocking this task?
	- Is this a repeating task, and if so, at what frequency?
- We should consider reviewing the task identification and handoff architecture to separate identifying a task in an inbox note from how it is added to Vikunja. I've heard that agents can hand tasks to agents, and if so, then this seems like it may be a good use case for it. I vaguely recall we discussed this previously. It may already be how we have designed the agent model where one agent acts as a "triage specialist" to identify different types of content and hands the items off to specialist agents for further action -- Vikunja task handler, calendar handler, etc.

  Assess this input, determine the current state of our model, and advise if this idea is on the right track relative to how commercial agent systems are built.
