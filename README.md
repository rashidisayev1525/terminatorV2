# terminator_bot

Known issue:

When two users are trying to book an appointment at the same time, captcha is being resolved for one user only. The other user is in a queue and (most likely) there will be timeout exception raised for captcha resolving. Captcha resolving task is in a while loop as some captchas are not resolved correctly. Due to this, a query timeout occurs:

`telegram.error.BadRequest: Query is too old and response timeout expired or query id is invalid`

Some messages could be added like (please wait as our captcha resolving solution is busy).

Todo:

No "Back" button, if user wants to change something, he/she needs to start from scratch by typing the /start command.
