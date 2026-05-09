import quickfix as fix
import quickfix44 as fix44


class FixMapper:
    @staticmethod
    def get_field(msg, field_obj):
        # Extracts a field value from a FIX message safely
        if msg.isSetField(field_obj):
            msg.getField(field_obj)
            return field_obj.getValue()
        return None

    @staticmethod
    def extract_new_order(msg):
        # Maps NewOrderSingle (35=D) fields to a dictionary
        oid, sym, side, qty, px = (
            fix.ClOrdID(),
            fix.Symbol(),
            fix.Side(),
            fix.OrderQty(),
            fix.Price(),
        )

        parties = []
        no_party_ids = fix.NoPartyIDs()
        if msg.isSetField(no_party_ids):
            msg.getField(no_party_ids)
            for i in range(1, no_party_ids.getValue() + 1):
                group = fix44.NewOrderSingle().NoPartyIDs()
                try:
                    msg.getGroup(i, group)
                except fix.FieldNotFound:
                    continue  # Skip if group is malformed or missing

                party_id = fix.PartyID()
                party_src = fix.PartyIDSource()
                party_role = fix.PartyRole()

                if group.isSetField(party_id):
                    group.getField(party_id)
                if group.isSetField(party_src):
                    group.getField(party_src)
                if group.isSetField(party_role):
                    group.getField(party_role)

                parties.append(
                    {
                        "id": (
                            party_id.getValue() if group.isSetField(party_id) else None
                        ),
                        "source": (
                            party_src.getValue()
                            if group.isSetField(party_src)
                            else None
                        ),
                        "role": (
                            party_role.getValue()
                            if group.isSetField(party_role)
                            else None
                        ),
                    }
                )

        return {
            "clord_id": FixMapper.get_field(msg, oid),
            "symbol": FixMapper.get_field(msg, sym),
            "side": str(FixMapper.get_field(msg, side)),
            "qty": FixMapper.get_field(msg, qty),
            "price": FixMapper.get_field(msg, px),
            "parties": parties,
        }

    @staticmethod
    def extract_cancel(msg):
        # Maps OrderCancelRequest (35=F) fields
        orig, oid, sym, side = (
            fix.OrigClOrdID(),
            fix.ClOrdID(),
            fix.Symbol(),
            fix.Side(),
        )
        return {
            "orig_clord_id": FixMapper.get_field(msg, orig),
            "clord_id": FixMapper.get_field(msg, oid),
            "symbol": FixMapper.get_field(msg, sym),
            "side": str(FixMapper.get_field(msg, side)),
        }

    @staticmethod
    def extract_replace(msg):
        # Maps OrderCancelReplaceRequest (35=G) fields
        orig, oid, sym, side, qty, px = (
            fix.OrigClOrdID(),
            fix.ClOrdID(),
            fix.Symbol(),
            fix.Side(),
            fix.OrderQty(),
            fix.Price(),
        )
        return {
            "orig_clord_id": FixMapper.get_field(msg, orig),
            "clord_id": FixMapper.get_field(msg, oid),
            "symbol": FixMapper.get_field(msg, sym),
            "side": str(FixMapper.get_field(msg, side)),
            "qty": FixMapper.get_field(msg, qty),
            "price": FixMapper.get_field(msg, px),
        }
