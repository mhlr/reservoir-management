# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.14.2
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# # Reservoir Management

# ## Problem Description

# From [Kowalik P, Rzemieniak M. Binary Linear Programming as a Tool of Cost Optimization for a Water Supply Operator. Sustainability. 2021 13(6):3470.](https://doi.org/10.3390/su13063470)

# > **The objective of the article is the minimization of the cost of electric power used by the pumps supplying water.**
#
# > The water supply system under consideration is that of a water supply operator based in a town with a population of about 25,000 inhabitants, located in Eastern Poland. **The main parts of the system are wells, pumps, a reservoir tank, and the distribution pipeline network.**
#
# > Supplied water is groundwater pumped from 7 wells. The capacities and values of the electric power of the pumps are presented in Table 1. **Water is pumped from the wells to a single reservoir tank with the capacity of Vmax** = 1500 m3 (the maximal volume of stored water).
#
# > **The demand for water varies over time**. **The outflow of water from the reservoir tank via the distribution network to customers is a continuous process.** For practical reasons, **predictions of demand are made for 24 one-hour timeslots**.
#
# > Controlling the pumps must obey the following requirements. **The pumps can operate with their nominal capacities only**, and the amount of water pumped by any pump depends on the time of operation only. **Each pump must operate for at least one hour per day.** Additionally, **at least one well and the pump integrated with it must be kept as a reserve at any moment of the day**. **The water inside the tank should be replaced at least once per day**. During standard operational conditions, **the volume of water in the reservoir tank cannot be less than Vmin** = 523.5 m3. It is the firefighting reserve, which is kept in order to satisfy an extra demand when a fire is extinguished by using water supplied from hydrants.
#
# > ... **the supplier of electric power does not use the same rate per MWh in its pricing** policy all day long. Instead, it uses three tariff levels ...
#
# > Various prices of electric power make efficient controlling of the pumps much moredifficult because the requirements resulting from the demand levels as well as technical and safety conditions should be satisfied at the lowest cost.
#
# > As it has already been mentioned above, a basically continuous process of water distribution is approximately described in a discrete form, namely by specifying 24 predicted values of the demand for 24 one-hour times slots.
#
# >  ... **in each timeslot, each pump can either be used or not**.

# + [markdown] tags=[]
# ## Problem instance data
# -

# From [Kowalik P, Rzemieniak M. Binary Linear Programming as a Tool of Cost Optimization for a Water Supply Operator. Sustainability. 2021 13(6):3470.](https://doi.org/10.3390/su13063470)

# %%file pumps.csv
id capacity power_consumption
1 75 15
2 133 37
3 157 33
4 176 33
5 59 22
6 69 33
7 120 22

# %%file tariff.csv
start end price
16 21 336.00
7 13 283.00
0 7 169.00
13 16 169.00
21 24 169.00

# %%file schedule.csv
time water_demand power_price
1 44.62 169
2 31.27 169
3 26.22 169
4 27.51 169
5 31.50 169
6 46.18 169
7 69.47 169
8 100.36 283
9 131.85 283
10 148.51 283
11 149.89 283
12 142.21 283
13 132.09 283
14 129.29 169
15 124.06 169
16 114.68 169
17 109.33 336
18 115.76 336
19 126.95 336
20 131.48 336
21 138.86 336
22 131.91 169
23 111.53 169
24 70.43 169

# %%file reservoir.csv
Vmin Vmax Vinit
523.5 1500 550

# + [markdown] tags=[]
# ## Load data

# + tags=[]
import itertools as it

import numpy as np
import pandas as pd

import dimod
from dwave import system as dw
# -

pumps = pd.read_csv("pumps.csv", sep=' ').set_index('id', drop=False)
schedule = pd.read_csv("schedule.csv", sep=' ').set_index('time', drop=False)
tariff = pd.read_csv("tariff.csv", sep=' ')
reservoir = pd.read_csv("reservoir.csv", sep=' ').loc[0]

# + [markdown] tags=[]
# ## Define domain language
# -

Sum = dimod.quicksum


# ### Inputs (Parameters)

# #### *The capacities and values of the electric power of the pumps are presented ...*

# +
def capacity(pump):
    return pumps.capacity[pump]

def power_consumption(pump):
    return pumps.power_consumption[pump]


# -

# #### *The supplier of electric power does not use the same rate per MWh in its pricing policy all day. It uses three tariff levels*

def power_price(time):
    return schedule.power_price[time]/1000


# #### *The demand for water varies over time*

def water_demand(time):
    return schedule.water_demand[time]


# ### Outputs (Variables)

# #### *In each timeslot, each pump can either be used or not*

def is_running(pump, time):
    return dimod.Binary(f"pump{pump}_time{time}")


# #### The state of the system is is the reservoir volume (implicit)

def reservoir_volume(time): 
    return (
        dimod.Real(f"volume_time{time}")
        if time >= schedule.time.min()
        else reservoir.Vinit
    )


# ### Derived terms

# #### *Water is pumped from the wells to a single reservoir tank*

def reservoir_inflow(time):
    return Sum(
            capacity(pump) * is_running(pump, time)
            for pump in pumps.id
        )


# #### *The outflow of water from the reservoir tank via the distribution network to customers is a continuous process*

def reservoir_outflow(time):
    return (
        reservoir_volume(time-1) + reservoir_inflow(time)
        - reservoir_volume(time)
    )


# #### Cost depends combined pump power use (implicit)

def power_used(time):
    return Sum(
            power_consumption(pump) * is_running(pump, time)
            for pump in pumps.id
        )


# ## Construct model

model = dimod.CQM()

# ### Define objective

# #### *The objective of the article is the minimization of the cost of electric power used by the pumps supplying water*

model.set_objective(
    Sum(
        power_price(time) * power_used(time)
        for time in schedule.time
    )
)

# + [markdown] tags=[]
# ### Add constraints
# -

# #### *Each pump must operate for at least one hour per day*

for pump in pumps.id:
    model.add_constraint(
        Sum(
            is_running(pump, time) for time in schedule.time
        ) >= 1,
        f"pump{pump}_on_at_least_1h_per_day")

# #### *At least one well and the pump integrated with it must be kept as a reserve at any moment of the day*

for time in schedule.time:
    model.add_constraint(
        Sum(
            is_running(pump, time) for pump in pumps.id
        ) <= pumps.shape[0] - 1,
        f"at_least_one_pump_in_reserve_at_time{time}" )

# #### *The water inside the tank should be replaced at least once per day* ??? (Not addressed in paper. Meaning?)

# +
# model.add_constraint(reservoir_volume(schedule.time.max()) >= reservoir.Vinit, f"water_in_tank_replaced");

# + tags=[] active=""
# ## Alternative (probably wrong) interpretation
# # model.add_constraint(
# #    Sum(
# #        reservoir_inflow(time) for time in schedule.time
# #    ) >= reservoir.Vinit,
# #    f"water_in_tank_replaced"
# #);
# -

# #### *The outflow of water from the reservoir tank via the distribution network to customers is a continuous process*

for time in schedule.time:
    model.add_constraint(
        reservoir_outflow(time) == water_demand(time),
        f"volume_at_time{time}"
    )

# #### *... a single reservoir tank with the capacity of Vmax*

for time in schedule.time:
    model.add_constraint(
        reservoir_volume(time) <= reservoir.Vmax,
        f"within_capacity_at_time{time}"
    )

# #### *The volume of water in the reservoir tank cannot be less than Vmin*

for time in schedule.time:
    model.add_constraint(
        reservoir_volume(time) >= reservoir.Vmin,
        f"sufficient_reserve_at_time{time}"
    )

# + [markdown] tags=[]
# ## Solve Model
# -

sampler = dw.LeapHybridCQMSampler()

# %%time
samples = sampler.sample_cqm(model, time_limit=20)
samples.resolve()

feasible = samples.filter(lambda d: d.is_feasible)

feasible.to_pandas_dataframe(True)

# ## Inspect model

lp_dump = dimod.lp.dumps(model)

print(lp_dump)

with open("reservoir.lp", "w") as f:
    print(lp_dump, file=f)
