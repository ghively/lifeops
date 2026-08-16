---
name: knowledge-os
description: |
  Integrate with the Knowledge OS to update tasks, create notes, and log progress.
  
  This skill allows you to interact with the user's knowledge management system.
  Use these tools to keep the user informed of your progress on tasks.
  
  When working on a task:
  1. Update status regularly using update_task_status
  2. Add progress updates with add_progress_update
  3. Create notes for your findings with create_note
  4. Log chat messages with add_chat_message
  
tools:
  update_task_status:
    description: Update the status of a task in the Knowledge OS
    args:
      task_id:
        type: string
        description: The UUID of the task
      status:
        type: string
        enum: [todo, in-progress, blocked, review, done]
        description: The new status
      current_action:
        type: string
        description: Brief description of what you're doing (e.g., "researching", "writing", "coding")
      notes:
        type: string
        description: Optional notes about progress or completion
    
  add_progress_update:
    description: Add a progress update to a task (visible to user in real-time)
    args:
      task_id:
        type: string
        description: The UUID of the task
      update:
        type: string
        description: What you've discovered or accomplished
    
  create_note:
    description: Create a new note from your research or work
    args:
      title:
        type: string
        description: Title of the note
      content:
        type: string
        description: Content/body of the note (supports markdown)
      tags:
        type: array
        description: Tags for the note
      related_task_id:
        type: string
        description: Optional task ID to link this note to
    
  add_chat_message:
    description: Add a message to the chat log
    args:
      session_id:
        type: string
        description: The chat session ID
      content:
        type: string
        description: The message content
      message_type:
        type: string
        enum: [agent, system]
        default: agent
      metadata:
        type: object
        description: Optional metadata like thoughts, tools used, etc.
    
  search_knowledge:
    description: Search the Knowledge OS for information
    args:
      query:
        type: string
        description: What to search for
      limit:
        type: integer
        default: 5
        description: Number of results to return
    
  get_object:
    description: Get a specific object by UUID from Qdrant
    args:
      object_id:
        type: string
        description: The UUID of the object to retrieve
---
