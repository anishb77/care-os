# CareOS

Originally called Pill Pilot, CareOS is a caregiver's caregiver that manages and optimizes complex medication schedules for people under their care.

# Description (from Devpost)

## Inspiration

Medication management can become surprisingly complicated when a caregiver is responsible for multiple people and medications. Different medications can have different preferred times, time windows, food requirements, and spacing rules, and real life rarely follows a perfect schedule.

Among the sea of options in benefiting the field of medical care, we initially considered building another medication reminder. But then, we realized that reminders only work when someone has already figured out the schedule. The harder problem is **creating and adapting that schedule in the first place**.

That became the idea behind CareOS: a tool designed not just to remind caregivers what to do, but to help determine **when everything should happen**.

## What it does

**CareOS is a dynamic medication scheduling tool for caregivers.** A caregiver enters the people they manage, their medications, and the scheduling rules that need to be followed. CareOS then generates a schedule that satisfies those rules while staying as close as possible to the caregiver's preferred times.

For example, a caregiver might specify:

* Medication A: around 8:00 AM
* Medication B: around 9:00 AM
* A and B: at least 2 hours apart
* B: must be taken with food

CareOS could resolve this into:

**8:00 AM: Medication A**
**10:00 AM: Medication B**

More importantly, the schedule isn't static. If Medication A is actually taken at **8:17 AM**, CareOS can use that real timestamp when recalculating the schedule, moving Medication B to **10:17 AM** if the spacing rule requires it.

If the caregiver misses or delays a dose, the remaining schedule can be recalculated accordingly.

This creates a core loop of:

**Define → Schedule → Take/Miss → Record → Recalculate**

CareOS is a scheduling tool, not a medical decision-maker. All medication rules and requirements are provided by the caregiver; CareOS does not determine dosages, medication compatibility, or medical recommendations.

## How we built it

We built CareOS using **Next.js and Node.js**, with **PostgreSQL through supabase.js and Supabase’s data API** for persistent data storage and authentication.

The most important part of the application is the scheduling engine. We envisioned the data model in a way that medications represent their scheduling rules, individual doses represent specific occurrences/instances, and schedules represent the arrangement of those doses.

The scheduling engine processes caregiver-defined constraints such as preferred times, time windows, meal requirements, medication ordering, and minimum spacing. When doses are taken, delayed, or missed, the system can use the new state to recalculate affected future doses.

We designed the product requirements and visual system ourselves, then used AI coding tools to accelerate implementation during the 48-hour hackathon.

## Challenges we ran into

Our biggest challenge was determining what problem CareOS should actually solve.

Our initial concept was much closer to a traditional medication reminder. As we developed the idea, we realized that simply reminding someone at a predetermined time didn't address the more interesting problem: **helping caregivers construct and maintain a schedule across multiple constraints.**

Turning that idea into a concrete scheduling system was challenging because we had to define which rules the engine should understand, how those rules should interact, and what should happen when they conflict.

On the implementation side, Supabase authentication was also a major learning curve for us, as we had very little previous experience implementing authentication and persistent user data.

Despite these challenges, we were able to turn the concept into a functional product within 48 hours, particularly as this was only our second hackathon.

## Accomplishments we're proud of

We're most proud of turning a relatively complex scheduling problem into a working product under a 48-hour deadline.

In particular, we were able to implement:

* Multi-person medication management
* Caregiver-defined scheduling constraints
* Automated schedule generation
* Conflict detection and resolution
* Taken and missed dose tracking
* Dynamic rescheduling based on actual dose times
* A focused caregiver-oriented interface

We're also proud of the product direction itself. Instead of building another static reminder system, we built around the idea that **the schedule should adapt to reality**.

## What we learned

This hackathon taught us a lot about product design and, more importantly, how much product design happens before writing code.

We learned that identifying a meaningful problem is only the beginning. We had to repeatedly narrow our concept, understand what caregivers would actually need, determine which features were essential, and make difficult scope decisions to keep the product achievable within 48 hours.

Technically, we also gained experience with authentication, persistent data, database-backed applications, and designing logic that has to handle interacting constraints rather than a simple linear workflow.

## What's next for CareOS

The next step for CareOS would be validating the concept with real caregivers and learning which scheduling problems are most common in practice.

From there, we would like to expand the scheduling engine, improve explanations when scheduling conflicts occur, add notifications, and eventually support more advanced caregiver workflows.

We would also want extensive safety testing and appropriate clinical review before the application were ever used as part of real-world medication management.

Our long-term goal is to make medication management less of a scheduling burden for caregivers by turning a complicated collection of rules into a plan that is easier to understand, follow, and adapt.
