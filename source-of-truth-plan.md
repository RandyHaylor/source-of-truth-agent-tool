goal: minimal source of truth system for ai agents to use when interacting with a user/instruction/higher level agent

requirements:
	system to store verbatim user statements and answers
		user statements = extracted raw input and n chars of output before (to contain questions the user might have been responding  yes/no/yes, but... to)
		see quickswarm engine raw user entry log streaming system that already does this. we'll simply use the local capturing system, but capture to a json that stores by timestamp, contains session-id, pre-user-submission-content, and user-submission text verbatim
			/home/aikenyon/ai_skills_agents_resources/userproject-on-rails-solution-concept/app-repo/quickswarm/raw_input_log
	system to store user requirements
		create new requirements node tree that contains ONLY references to the raw entries
		based on a json schema we'll define
		multiple top level entries allowed
		highest level lists relevant session jsonl files and their paths
		the ai agent can supply no raw text, only valid references to raw user log entries (which contain the pre-text and user submission).  
		If a user submission is over a threshold (only if), the agent can specify a range from the entry.
		This way the requirements tree, which is to be referenced, and it's top level node(s) injected regularly into conversation context, is the only source of truth. This leaves the limiting pathway for ai to hallucinate requirements it's ability to selectively choose the wrong quotes, etc, so adding a review/approving layer is appropriate.
			an agent session using a -p call and a persistent session will be given access to requirements, user quotes, and the session jsonl conversation and project folder/files (read only, web request tools for fact checking, no other tools), and can deny a requirements tree modification with a message on what to adjust.
			
			
Technical requirements for integration with any ai (points where we want interface separation to allow use on ai cli systems other than claude cli): a hook for user prompt submission, a way to access raw message history and storage location for conversation, a way to build, store, save, and edit the requirements tree, a way to inject the top n level nodes into conversation either periodically, on sub-agent calls. ability to allow the primary ai agent to interact with the node tree json via a controlled api (the heart of our app, which will be python and cross platform) for read/write, and to also read but not write to the raw user log. raw user log will not support conversation rewind or compact, and therefore user log is just a repository of quotes to draw from and not itself a hard source of truth - only the node tree of references to quotes is.
