import quickfix as fix

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
        oid, sym, side, qty, px = fix.ClOrdID(), fix.Symbol(), fix.Side(), fix.OrderQty(), fix.Price()
        return {
            "clord_id": FixMapper.get_field(msg, oid),
            "symbol":   FixMapper.get_field(msg, sym),
            "side":     str(FixMapper.get_field(msg, side)),
            "qty":      FixMapper.get_field(msg, qty),
            "price":    FixMapper.get_field(msg, px)
        }

    @staticmethod
    def extract_cancel(msg):
        # Maps OrderCancelRequest (35=F) fields
        orig, oid, sym, side = fix.OrigClOrdID(), fix.ClOrdID(), fix.Symbol(), fix.Side()
        return {
            "orig_clord_id": FixMapper.get_field(msg, orig),
            "clord_id":      FixMapper.get_field(msg, oid),
            "symbol":         FixMapper.get_field(msg, sym),
            "side":           str(FixMapper.get_field(msg, side))
        }

    @staticmethod
    def extract_replace(msg):
        # Maps OrderCancelReplaceRequest (35=G) fields
        orig, oid, sym, side, qty, px = fix.OrigClOrdID(), fix.ClOrdID(), fix.Symbol(), fix.Side(), fix.OrderQty(), fix.Price()
        return {
            "orig_clord_id": FixMapper.get_field(msg, orig),
            "clord_id":      FixMapper.get_field(msg, oid),
            "symbol":         FixMapper.get_field(msg, sym),
            "side":           str(FixMapper.get_field(msg, side)),
            "qty":            FixMapper.get_field(msg, qty),
            "price":          FixMapper.get_field(msg, px)
        }
