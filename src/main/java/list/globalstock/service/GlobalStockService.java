package list.globalstock.service;

import list.globalstock.dto.GlobalStockDto;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
public class GlobalStockService {

    public List<GlobalStockDto> getGlobalStock() throws IOException {
        List<GlobalStockDto> result = new ArrayList<>();

        String url = "https://m.stock.naver.com/worldstock/home/USA/marketValue/NASDAQ";
        Document doc = Jsoup.connect(url).get();
        Elements rows = doc.select("table.TableComm_table__g2z0R tbody tr");

        for(Element row : rows) {
            if(result.size() >= 10) break;

            String name = row.select("span.TableComm_symbolCode__.+").text();
            String price = row.select("td").get(4).text();
            String rate = row.select("td").get(2).text();

            result.add(new GlobalStockDto(name, price, rate));

        }

        return result;
    }

}
