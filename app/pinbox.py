"""Wrong guesses at the PIN, counted per box.

There are three places in this app that take the parent PIN, and they are three
boxes because they are reached from three different places by different people:

- **the sums overlay** (`POST /api/quiz/grownup`) - on the child's own page, so
  it is the one a child can reach without finding anything;
- **the parent page's gate** (`main._parent()` and `_grownup()`) - the PIN as a
  header, which is the only one of the three nobody types;
- **changing the PIN** (`POST /api/parent/pin`) - inside the parent page, and
  getting it hands over the page itself.

**Each keeps its own five tries and refuses on its own count.** Two things go
wrong when they share one, and the second is not obvious until the first is
fixed:

- *Sharing the count leaves boxes unthrottled.* Reaching a route inside the
  parent page means passing `main._parent()`, and a browser with the PIN in its
  sessionStorage sends a correct header without anybody typing anything, so
  anything that cleared a shared count on a correct header cleared it before
  every guess.
- *Sharing the **refusal** lets one box lock another.* The gate used to refuse
  on the sums box's count. Once that count stopped being wiped every thirty
  seconds, five wrong guesses at a box on the child's own screen would have
  shut a parent out of the parent page for ten minutes - and out of the typed
  PIN that is the way back. A child could have done it on purpose, or by
  poking at the overlay, and the parent would have had no idea why.

The cost of separating them is that a guesser working through all three gets
fifteen tries in ten minutes rather than five. That is the right trade: fifteen
is still nothing against even a four-digit PIN, every one of the fifteen is
written to the activity log and alerted on by `main._bad_pin()`, and the thing
bought with it is that no box can be used to disable another. The alternative -
one lockout for everything - is a child-operated off switch for their parent's
settings page.

**This is its own module rather than three lists across `main.py` and
`quiz.py`**, and the reason is `/unlock`. `app/telegram.py` offers a parent
locked out by somebody else's guessing a way back in, and says in so many words
that it clears the wrong-PIN lockout. It cannot import `main` - `main` imports
it - so for as long as these lived in `main` that sentence could only ever be
true of the one `quiz` happened to hold, and it was said anyway. State two
modules need is state that belongs to neither of them.

Nothing here imports anything else in the app, deliberately: this is the module
at the bottom that both of the others can reach.

**In memory, not in the database.** A lockout is ten minutes long and a restart
is the parent's own doing; persisting it would mean a child could wait out a
lockout by getting the app restarted, or - worse - that a bug in the store
could lock a household out of its own settings page.
"""

import time

# Five wrong PINs and the box stops answering for ten minutes. A four-digit PIN
# is ten thousand guesses, which is nothing to a script and an afternoon to a
# bored child.
MAX_TRIES = 5
LOCKOUT = 600


class PinBox:
    """One place the PIN is typed, and the wrong guesses made there."""

    def __init__(self, name: str, where: str):
        # `name` is for `/unlock`'s reply and for the log; `where` is the
        # sentence `main._bad_pin()` puts in the alert to a parent.
        self.name = name
        self.where = where
        self.tries: list[float] = []

    def locked_for(self) -> int:
        """Seconds until this box will answer again, 0 if it will now.

        Sliding, not latching: five guesses an hour apart never lock anything,
        and the window is measured from the oldest guess still inside it.
        """
        now = time.time()
        recent = [t for t in self.tries if t > now - LOCKOUT]
        self.tries[:] = recent
        if len(recent) < MAX_TRIES:
            return 0
        return int(recent[0] + LOCKOUT - now) + 1

    def note(self) -> int:
        """Count one wrong guess, and say how many there have been in the
        window. The count is what the alert reports: "one wrong try" and "five
        wrong tries" are different things to be told."""
        now = time.time()
        self.tries.append(now)
        return len([t for t in self.tries if t > now - LOCKOUT])

    def waiting(self) -> int:
        """How many guesses are still inside the window. 0 means this box has
        nothing to forgive, which is what `/unlock` needs to know before it
        claims to have forgiven something."""
        now = time.time()
        self.tries[:] = [t for t in self.tries if t > now - LOCKOUT]
        return len(self.tries)

    def clear(self) -> None:
        self.tries.clear()


# The sums overlay's. `app/quiz.py` still owns the *questions* and the day
# cookie; this is only the counter, and it lives here rather than there so that
# there is one implementation of the window arithmetic and one place to ask
# about any of the boxes.
SHARED = PinBox("the grown-up box on the sums", "grown-up box on the sums")
# The PIN as a header. `_parent()` and `_grownup()` share this one because they
# are the same credential presented the same way, by the same browser, and
# splitting them would only be two ways to spend five guesses.
GATE = PinBox("the parent page", "parent page")
PIN_CHANGE = PinBox("changing the PIN", "changing the PIN")

ALL = (SHARED, GATE, PIN_CHANGE)


def clear_all() -> list[str]:
    """Forgive every box, and say which ones actually had something waiting.

    The names come back rather than a count, because the one caller is
    `/unlock` telling a parent what it just did, and "cleared the lockout" when
    there was no lockout is the kind of true-sounding sentence that stops
    people trusting the next one.
    """
    forgiven = [box.name for box in ALL if box.waiting()]
    for box in ALL:
        box.clear()
    return forgiven


def locked() -> list[str]:
    """The boxes that are refusing to answer right now, by name."""
    return [box.name for box in ALL if box.locked_for()]
