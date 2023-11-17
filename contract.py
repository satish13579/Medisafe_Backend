import beaker
import pyteal as pt
from beaker.decorators import Authorize

class MyAppState:
    patient_count = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        default=pt.Int(0),
        descr="No.of Patients Opted in MEDISAFE"
        )
    doctor_count = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        default=pt.Int(0),
        descr="No.of Doctors Opted in MEDISAFE"
        )
    records_issued = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64, 
        default=pt.Int(0),
        descr="No.of Records Issued Using MEDISAFE"
        )
    name= beaker.LocalStateValue(
        stack_type=pt.TealType.bytes,
        descr="Name of the user"
        )
    DOB = beaker.LocalStateValue(
        stack_type=pt.TealType.bytes,
        descr="Date of Birth of the User"
    )
    role = beaker.LocalStateValue(
        stack_type=pt.TealType.bytes,
        descr="Determines the Type of User"
    )
    reserved_local_value = beaker.ReservedLocalStateValue(
        stack_type=pt.TealType.bytes,
        max_keys=2,
        descr="reserved state to define seprate keys for different roles"
    )

app = beaker.Application('MEDISAFE', state=MyAppState())


@app.create
def create():
    return app.initialize_global_state()

@app.opt_in
def account_optin(name:pt.abi.String,role:pt.abi.String,dob:pt.abi.String,*,output:pt.abi.String):
    return pt.Seq(
        pt.If(pt.Or(
                pt.Eq(role.get(),pt.Bytes("PATIENT")),
                pt.Eq(role.get(),pt.Bytes("DOCTOR"))
                ),
                pt.Seq(app.initialize_local_state(),
                        app.state.name.set(name.get()),
                        app.state.role.set(role.get()),
                        app.state.DOB.set(dob.get()),
                        pt.If(pt.Eq(role.get(),pt.Bytes("PATIENT")),pt.Seq(app.state.reserved_local_value[pt.Bytes("access_hash")].set(pt.Bytes("0")),app.state.reserved_local_value[pt.Bytes("data_hash")].set(pt.Bytes("0")),app.state.patient_count.increment()),pt.Seq(app.state.reserved_local_value[pt.Bytes("request_hash")].set(pt.Bytes("0")),app.state.doctor_count.increment())),
                        output.set(pt.Bytes("Success"))
                        ),
                output.set(pt.Bytes("Role Must Be Only Patient or Doctor"),)
        ),
        pt.If(pt.Eq(output.get(),pt.Bytes("Success")),pt.Approve(),pt.Reject())
    )

@app.clear_state()
def cs():
    return pt.Seq(pt.If(app.state.role==pt.Bytes("PATIENT")).Then(
        app.state.patient_count.decrement()
    ).ElseIf(app.state.role==pt.Bytes("DOCTOR")).Then(
        app.state.doctor_count.decrement()
    ))

@app.external(authorize=Authorize.opted_in())
def add_request_hash(hash:pt.abi.String,*,output:pt.abi.String):
    return pt.Seq(
        pt.If(app.state.role==pt.Bytes("DOCTOR")).Then(
            app.state.reserved_local_value[pt.Bytes("request_hash")].set(hash.get()),output.set(pt.Bytes("Success")),pt.Approve()
        ).Else(
            output.set(pt.Bytes("You Can't Access This Method")),pt.Reject()
        )
    )

@app.external(authorize=Authorize.opted_in())
def add_access_hash(hash:pt.abi.String,*,output:pt.abi.String):
    return pt.Seq(
        pt.If(app.state.role==pt.Bytes("PATIENT")).Then(
            app.state.reserved_local_value[pt.Bytes("access_hash")].set(hash.get()),output.set(pt.Bytes("Success")),pt.Approve()
        ).Else(
            output.set(pt.Bytes("You Can't Access This Method")),pt.Reject()
        )
    )

@app.external(authorize=Authorize.opted_in())
def add_data_hash(hash:pt.abi.String,*,output:pt.abi.String):
    return pt.Seq(
        pt.If(app.state.role==pt.Bytes("PATIENT")).Then(
            app.state.reserved_local_value[pt.Bytes("data_hash")].set(hash.get()),output.set(pt.Bytes("Success")),app.state.records_issued.increment(),pt.Approve()
        ).Else(
            output.set(pt.Bytes("You Can't Access This Method")),pt.Reject()
        )
    )

# Rest of the code...
if __name__ == '__main__':
    spec = app.build()
    spec.export('artifacts')
